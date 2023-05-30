"""Builds a CLI, Webhook, and Gradio app for Q&A on the Full Stack corpus.

For details on corpus construction, see the accompanying notebook."""
import modal
from fastapi import FastAPI

import vecstore
from utils import pretty_log

# definition of our container image for jobs on Modal
# Modal gets really powerful when you start using multiple images!
image = modal.Image.debian_slim(  # we start from a lightweight linux distro
    python_version="3.10"  # we add a recent Python version
).pip_install(  # and we install the following packages:
    "langchain~=0.0.145",
    # 🦜🔗: a framework for building apps with LLMs
    "openai~=0.26.3",
    # high-quality language models and cheap embeddings
    "tiktoken",
    # tokenizer for OpenAI models
    "faiss-cpu",
    # vector storage and similarity search
    "pymongo[srv]==3.11",
    # python client for MongoDB, our data persistence solution
    "gradio~=3.17",
    # simple web UIs in Python, from 🤗
    "gantry==0.5.6",
    # 🏗️: monitoring, observability, and continual improvement for ML systems
)

# we define a Stub to hold all the pieces of our app
# most of the rest of this file just adds features onto this Stub
stub = modal.Stub(
    name="ask-fsdl",
    image=image,
    secrets=[
        # this is where we add API keys, passwords, and URLs, which are stored on Modal
        modal.Secret.from_name("mongodb-fsdl"),
        modal.Secret.from_name("openai-api-key-fsdl"),
        modal.Secret.from_name("gantry-api-key"),
    ],
    mounts=[
        # we make our local modules available to the container
        *modal.create_package_mounts(module_names=["vecstore", "docstore", "utils"])
    ],
)

VECTOR_DIR = vecstore.VECTOR_DIR
vector_storage = modal.SharedVolume().persist("vector-vol")


@stub.function(
    image=image,
    shared_volumes={
        str(VECTOR_DIR): vector_storage,
    },
)
@modal.web_endpoint(method="GET", label="ask-fsdl-hook")
def web(query: str, request_id=None):
    """Exposes our Q&A chain for queries via a web endpoint."""
    pretty_log(
        f"handling request with client-provided id: {request_id}"
    ) if request_id else None
    answer = qanda_langchain(query, request_id=request_id, with_logging=True)
    return {"answer": answer}


def qanda_langchain(query: str, request_id=None, with_logging=False) -> str:
    """Runs sourced Q&A for a query using LangChain.

    Arguments:
        query: The query to run Q&A on.
        request_id: A unique identifier for the request.
        with_logging: If True, logs the interaction to Gantry.
    """
    from langchain.chains.qa_with_sources import load_qa_with_sources_chain
    from langchain.llms import OpenAI

    import vecstore

    embedding_engine = vecstore.get_embedding_engine(allowed_special="all")

    pretty_log("connecting to vector storage")
    vector_index = vecstore.connect_to_vector_index(
        vecstore.INDEX_NAME, embedding_engine
    )
    pretty_log("connected to vector storage")

    pretty_log(f"running on query: {query}")
    pretty_log("selecting sources by similarity to query")
    sources = vector_index.similarity_search(query, k=5)

    if with_logging:
        pretty_log("SOURCES")
        print(*[source.page_content for source in sources], sep="\n\n---\n\n")

    pretty_log("running query against Q&A chain")

    llm = OpenAI(model_name="text-davinci-003", temperature=0)
    chain = load_qa_with_sources_chain(llm, chain_type="stuff")

    result = chain(
        {"input_documents": sources, "question": query}, return_only_outputs=True
    )
    answer = result["output_text"]

    if with_logging:
        print(answer)
        pretty_log("logging results to gantry")
        record_key = log_event(query, sources, answer, request_id=request_id)
        pretty_log(f"logged to gantry with key {record_key}")

    return answer


@stub.function(
    image=image,
    shared_volumes={
        str(VECTOR_DIR): vector_storage,
    },
    cpu=8.0,  # use more cpu for vector storage creation
)
def sync_vector_db_to_doc_db():
    """Syncs the vector index onto the document storage."""
    import docstore

    document_client = docstore.connect()
    pretty_log("connected to document DB")

    embedding_engine = vecstore.get_embedding_engine(allowed_special="all")

    docs = docstore.get_documents(document_client)

    pretty_log("splitting into bite-size chunks")
    ids, texts, metadatas = prep_documents_for_vector_storage(docs)

    pretty_log(f"sending to vector store {vecstore.INDEX_NAME}")
    vector_index = vecstore.create_vector_index(
        vecstore.INDEX_NAME, embedding_engine, texts, metadatas
    )
    vector_index.save_local(folder_path=VECTOR_DIR, index_name=vecstore.INDEX_NAME)
    pretty_log(f"vector store {vecstore.INDEX_NAME} created")


@stub.function(image=image)
def flush_doc_db():
    """Empties the document storage."""
    import docstore

    docstore.flush()


def log_event(query: str, sources, answer: str, request_id=None):
    """Logs the event to Gantry."""
    import os

    import gantry

    gantry.init(api_key=os.environ["GANTRY_API_KEY"], environment="modal")

    application = "ask-fsdl"
    join_key = str(request_id) if request_id else None

    inputs = {"question": query}
    inputs["docs"] = "\n\n---\n\n".join(source.page_content for source in sources)
    inputs["sources"] = "\n\n---\n\n".join(
        source.metadata["source"] for source in sources
    )
    outputs = {"answer_text": answer}

    record_key = gantry.log_record(
        application=application, inputs=inputs, outputs=outputs, join_key=join_key
    )

    return record_key


def prep_documents_for_vector_storage(documents):
    """Prepare documents from document store for embedding and vector storage.

    Documents are split into chunks so that they can be used with sourced Q&A.

    Arguments:
        documents: A list of LangChain.Documents with text, metadata, and a hash ID.
    """
    from langchain.text_splitter import RecursiveCharacterTextSplitter

    text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        chunk_size=500, chunk_overlap=100, allowed_special="all"
    )
    ids, texts, metadatas = [], [], []
    for document in documents:
        text, metadata = document["text"], document["metadata"]
        doc_texts = text_splitter.split_text(text)
        doc_metadatas = [metadata] * len(doc_texts)
        ids += [metadata.get("sha256")] * len(doc_texts)
        texts += doc_texts
        metadatas += doc_metadatas

    return ids, texts, metadatas


@stub.function(
    image=image,
    shared_volumes={
        str(VECTOR_DIR): vector_storage,
    },
)
def cli(query: str):
    answer = qanda_langchain(query, with_logging=False)
    pretty_log("🦜 ANSWER 🦜")
    print(answer)


web_app = FastAPI()


@web_app.get("/")
async def root():
    return {"message": "Hello World"}


@stub.function(
    image=image,
    shared_volumes={
        str(VECTOR_DIR): vector_storage,
    },
)
@modal.asgi_app(label="ask-fsdl")
def fastapi_app():
    """A simple Gradio interface for debugging."""
    import gradio as gr
    from gradio.routes import mount_gradio_app

    def chain_with_logging(*args, **kwargs):
        return qanda_langchain(*args, with_logging=True, **kwargs)

    interface = gr.Interface(
        fn=chain_with_logging,
        inputs="text",
        outputs="text",
        title="Ask Questions About Full Stack Deep Learning.",
        examples=[
            "What is zero-shot chain-of-thought prompting?",
            "Would you rather fight 100 LLaMA-sized GPT-4s or 1 GPT-4-sized LLaMA?",
            "What are the differences in capabilities between GPT-3 davinci and GPT-3.5 code-davinci-002?",  # noqa: E501
            "What is PyTorch? How can I decide whether to choose it over TensorFlow?",
            "Is it cheaper to run experiments on cheap GPUs or expensive GPUs?",
            "How do I recruit an ML team?",
            "What is the best way to learn about ML?",
        ],
        allow_flagging="never",
    )

    return mount_gradio_app(app=web_app, blocks=interface, path="/gradio")


@stub.function(
    image=image,
    interactive=True,
    shared_volumes={
        str(VECTOR_DIR): vector_storage,
    },
    timeout=3600,
)
def debug():
    """Convenient debugging access to Modal."""
    import IPython

    IPython.embed()
