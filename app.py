import modal
import time
from fastapi import FastAPI
from fastapi.responses import RedirectResponse

import vecstore
from utils import pretty_log

# definition of our container image for jobs on Modal
image = modal.Image.debian_slim(python_version="3.10").pip_install(
    "langchain==0.0.184",
    "openai~=0.27.7",
    "tiktoken",
    "faiss-cpu",
    "pymongo[srv]==3.11",
    "gradio~=3.34",
    "gantry==0.5.6",
)

# Pre-load vector index on startup
vector_index = None
VECTOR_DIR = vecstore.VECTOR_DIR
vector_storage = modal.NetworkFileSystem.persisted("vector-vol")

# Keep multiple instances warm to prevent cold starts
stub = modal.Stub(
    name="askfsdl-backend",
    image=image,
    secrets=[
        modal.Secret.from_name("mongodb-fsdl"),
        modal.Secret.from_name("openai-api-key-fsdl"),
        modal.Secret.from_name("gantry-api-key-fsdl"),
    ],
    mounts=[modal.Mount.from_local_python_packages("vecstore", "docstore", "utils", "prompts")],
)

# Pre-load the vector index during startup
@stub.function(image=image, keep_warm=3)
@modal.web_endpoint(method="GET")
async def web(query: str, request_id=None):
    """Exposes our Q&A chain for queries via a web endpoint."""
    start_time = time.time()
    if request_id:
        pretty_log(f"handling request with client-provided id: {request_id}")

    # Check if vector index is loaded
    if vector_index is None:
        load_vector_index()

    answer = await qanda_async(query, request_id=request_id, with_logging=bool(os.environ.get("GANTRY_API_KEY")))
    elapsed_time = time.time() - start_time
    pretty_log(f"Total time for query: {elapsed_time} seconds")
    
    return {"answer": answer}

# Load vector index at startup
def load_vector_index():
    global vector_index
    pretty_log("Loading vector index...")
    embedding_engine = vecstore.get_embedding_engine(allowed_special="all")
    vector_index = vecstore.connect_to_vector_index(vecstore.INDEX_NAME, embedding_engine)
    pretty_log("Vector index loaded with {vector_index.index.ntotal} vectors")

@stub.function(image=image, keep_warm=3)
async def qanda_async(query: str, request_id=None, with_logging: bool = False) -> str:
    """Runs sourced Q&A for a query using LangChain asynchronously."""
    from langchain.chains.qa_with_sources import load_qa_with_sources_chain
    from langchain.chat_models import ChatOpenAI
    import prompts

    # Use GPT-3.5 for faster response time in latency-critical situations
    llm = ChatOpenAI(model_name="gpt-3.5-turbo", temperature=0, max_tokens=256)

    pretty_log(f"Running query: {query}")
    pretty_log("Selecting sources by similarity to query")

    # Reduce the number of sources to improve performance
    sources_and_scores = vector_index.similarity_search_with_score(query, k=2)
    sources, scores = zip(*sources_and_scores)

    pretty_log("Running query against Q&A chain")
    chain = load_qa_with_sources_chain(
        llm,
        chain_type="stuff",
        verbose=with_logging,
        prompt=prompts.main,
        document_variable_name="sources",
    )

    result = chain({"input_documents": sources, "question": query}, return_only_outputs=True)
    answer = result["output_text"]

    if with_logging:
        pretty_log("Logging results to Gantry")
        record_key = log_event(query, sources, answer, request_id=request_id)
        if record_key:
            pretty_log(f"Logged to Gantry with key {record_key}")

    return answer

# Function for logging events to Gantry
def log_event(query: str, sources, answer: str, request_id=None):
    import os
    import gantry

    if not os.environ.get("GANTRY_API_KEY"):
        pretty_log("No Gantry API key found, skipping logging")
        return None

    gantry.init(api_key=os.environ["GANTRY_API_KEY"], environment="modal")

    application = "ask-fsdl"
    join_key = str(request_id) if request_id else None

    inputs = {"question": query}
    inputs["docs"] = "\n\n---\n\n".join(source.page_content for source in sources)
    inputs["sources"] = "\n\n---\n\n".join(source.metadata["source"] for source in sources)
    outputs = {"answer_text": answer}

    record_key = gantry.log_record(
        application=application, inputs=inputs, outputs=outputs, join_key=join_key
    )
    return record_key

# Startup function for FastAPI web app
web_app = FastAPI(docs_url=None)

@web_app.get("/")
async def root():
    return {"message": "See /gradio for the dev UI."}

@web_app.get("/docs", response_class=RedirectResponse, status_code=308)
async def redirect_docs():
    """Redirects to the Gradio subapi docs."""
    return "/gradio/docs"

# Mount Gradio app for debugging
@stub.function(image=image, keep_warm=3)
@modal.asgi_app(label="askfsdl-backend")
def fastapi_app():
    """A simple Gradio interface for debugging."""
    import gradio as gr
    from gradio.routes import App

    inputs = gr.TextArea(label="Question", value="What is zero-shot chain-of-thought prompting?", show_label=True)
    outputs = gr.TextArea(label="Answer", value="The answer will appear here.", show_label=True)

    interface = gr.Interface(
        fn=qanda_async,
        inputs=inputs,
        outputs=outputs,
        title="Ask Questions About The Full Stack.",
        description="Get answers with sources from an LLM.",
        allow_flagging="never",
        theme=gr.themes.Default(radius_size="none", text_size="lg"),
        article="# GitHub Repo: https://github.com/the-full-stack/ask-fsdl",
    )

    gradio_app = App.create_app(interface)
    web_app.mount("/gradio", gradio_app)
    return web_app