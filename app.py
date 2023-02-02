"""Builds a CLI, Webhook, and Gradio app for LLM Q&A on the FSDL Corpus.

For details on corpus construction, see the accompanying notebook."""
from pathlib import Path

from fastapi import FastAPI
import modal


image = modal.Image.debian_slim(python_version="3.10").pip_install(
    "langchain~=0.0.7",
    "openai~=0.26.3",
    "pinecone-client",
    "pymongo==3.11",
    "gradio~=3.17",
    "gantry==0.5.6",
    "tiktoken",
)

stub = modal.Stub(
    name="ask-fsdl",
    image=image,
    secrets=[
        modal.Secret.from_name("pinecone-api-key"),
        modal.Secret.from_name("openai-api-key"),
        modal.Secret.from_name("mongodb"),
        modal.Secret.from_name("gantry-api-key"),
    ],
)

PINECONE_INDEX = "openai-ada-fsdl"

# Terminal codes for pretty-printing.
START, END = "\033[1;38;5;214m", "\033[0m"


def pretty_log(str):
    print(f"{START}🥞: {str}{END}")


@stub.function(
    image=image,
)
def sync_vector_db_to_doc_db():
    import os

    from langchain.embeddings import OpenAIEmbeddings
    from langchain.text_splitter import CharacterTextSplitter
    from langchain.vectorstores import Pinecone
    import openai
    import pinecone
    import pymongo

    ###
    # Connect to Document DB
    ###

    mongodb_password = os.environ["MONGODB_PASSWORD"]
    mongodb_uri = os.environ["MONGODB_URI"]
    connection_string = f"mongodb+srv://fsdl:{mongodb_password}@{mongodb_uri}/?retryWrites=true&w=majority"
    client = pymongo.MongoClient(connection_string)
    pretty_log("connected to document DB")

    ###
    # Connect to VectorDB
    ###

    pinecone_api_key = os.environ["PINECONE_API_KEY"]
    pinecone.init(api_key=pinecone_api_key, environment="us-east1-gcp")
    pretty_log("connected to vector DB")

    ###
    # Spin up EmbeddingEngine
    ###

    openai.api_key = os.environ["OPENAI_API_KEY"]
    base_embeddings = OpenAIEmbeddings()

    ###
    # Retrieve Documents
    ###

    db = client.get_database("fsdl")
    collection = db.get_collection("ask-fsdl")

    pretty_log(f"pulling documents from {collection.full_name}")
    docs = collection.find()

    ###
    # Chunk Documents and Spread Sources
    ###
    pretty_log("splitting into bite-size chunks")

    text_splitter = CharacterTextSplitter.from_tiktoken_encoder(
        chunk_size=500,
        chunk_overlap=100,
    )
    ids, texts, metadatas = [], [], []
    for document in docs:
        text, metadata = document["text"], document["metadata"]
        doc_texts = text_splitter.split_text(text)
        doc_metadatas = [metadata] * len(doc_texts)
        ids += [document["sha256"]] * len(doc_texts)
        texts += doc_texts
        metadatas += doc_metadatas

    ###
    # Upsert to VectorDB
    ###

    pretty_log(f"sending to vectorDB {PINECONE_INDEX}")
    Pinecone.from_texts(
        texts, base_embeddings, metadatas=metadatas, ids=ids, index_name=PINECONE_INDEX
    )


def qanda_langchain(query: str, request_id=None, with_logging=False) -> str:
    import os

    import gantry
    from langchain.chains.qa_with_sources import load_qa_with_sources_chain
    from langchain.embeddings.openai import OpenAIEmbeddings
    from langchain.llms import OpenAI
    from langchain.text_splitter import CharacterTextSplitter
    from langchain.vectorstores import Pinecone
    import openai
    import pinecone

    ###
    # Embed Query
    ###
    openai.api_key = os.environ["OPENAI_API_KEY"]
    base_embeddings = OpenAIEmbeddings()

    ###
    # Connect to VectorDB
    ###
    pretty_log("connecting to Pinecone")
    pinecone_api_key = os.environ["PINECONE_API_KEY"]
    pinecone.init(api_key=pinecone_api_key, environment="us-east1-gcp")
    docsearch = Pinecone.from_existing_index(index_name=PINECONE_INDEX, embedding=base_embeddings)

    ###
    # Run docsearch
    ###
    pretty_log(f"running on query: {query}")
    pretty_log(f"selecting sources by similarity to query")
    docs = docsearch.similarity_search(query)

    ###
    # Run chain
    ###
    pretty_log("running query against Q&A chain")
    chain = load_qa_with_sources_chain(
        OpenAI(temperature=0,), chain_type="stuff"
    )
    result = chain(
        {"input_documents": docs, "question": query}, return_only_outputs=True
    )
    answer = result["output_text"]

    ###
    # Log results
    ###
    if with_logging:
        pretty_log("logging results to gantry")
        gantry.init(api_key=os.environ["GANTRY_API_KEY"], environment="modal")

        application = "ask-fsdl"
        join_key = str(request_id) if request_id else None

        inputs = {"question": query}
        inputs["docs"] = "\n\n---\n\n".join(doc.page_content for doc in docs)
        inputs["sources"] = "\n\n---\n\n".join(doc.metadata["source"] for doc in docs)
        outputs = {"answer_text": answer}

        record_key = gantry.log_record(application=application, inputs=inputs, outputs=outputs, join_key=join_key)
        pretty_log(f"logged to gantry with key {record_key}")

    return answer


@stub.webhook(method="GET", label="ask-fsdl-hook")
def web(query: str, request_id=None):
    pretty_log(f"handling request with client-provided id: {request_id}") if request_id else None
    answer = qanda_langchain(query, request_id=request_id, with_logging=True)
    return {
        "answer": answer,
    }


@stub.function(image=image)
def cli(query: str):
    answer = qanda_langchain(query)
    pretty_log(f"🦜 ANSWER 🦜")
    print(answer)


web_app = FastAPI()


# Wrap in a Gradio interface for debugging backend
@stub.asgi(
    image=image,
    label="ask-fsdl",
    )
def fastapi_app():
    import gradio as gr
    from gradio.routes import mount_gradio_app

    def chain_with_logging(*args, **kwargs):
        return qanda_langchain(*args, with_logging=True, **kwargs)

    interface = gr.Interface(
        fn=chain_with_logging,
        inputs="text",
        outputs="text",
        title="Ask Questions About Deep Learning.",
        examples=[
            "What is PyTorch? How can I decide whether to choose it over TensorFlow?",
            "Is it cheaper to run experiments on cheap GPUs or expensive GPUs?",
            "How do I recruit an ML team?",
            ],
        allow_flagging="never",
    )

    return mount_gradio_app(
        app=web_app,
        blocks=interface,
        path="/gradio"
    )

# Add a debugging access point on Modal
@stub.function(
    image=image,
    interactive=True
    )
def debug():
    import IPython
    IPython.embed()
