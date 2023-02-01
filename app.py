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
    "tiktoken",
)
stub = modal.Stub(
    name="ask-fsdl",
    image=image,
    secrets=[
        modal.Secret.from_name("pinecone-api-key"), modal.Secret.from_name("openai-api-key"), modal.Secret.from_name("mongodb")
    ],
)

PINECONE_INDEX = "openai-ada-fsdl"


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
    print("🥞: connected to document DB")

    ###
    # Connect to VectorDB
    ###

    pinecone_api_key = os.environ["PINECONE_API_KEY"]
    pinecone.init(api_key=pinecone_api_key, environment="us-east1-gcp")
    print("🥞: connected to vector DB")

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

    print(f"🥞: pulling documents from {collection.full_name}")
    docs = collection.find()

    ###
    # Chunk Documents and Spread Sources
    ###
    print("🥞: splitting into bite-size chunks")

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

    print(f"🥞: sending to vectorDB {PINECONE_INDEX}")
    Pinecone.from_texts(
        texts, base_embeddings, metadatas=metadatas, ids=ids, index_name=PINECONE_INDEX
    )


def qanda_langchain(query: str) -> tuple[str, list[str]]:
    import os

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
    print("🥞: connecting to Pinecone")
    pinecone_api_key = os.environ["PINECONE_API_KEY"]
    pinecone.init(api_key=pinecone_api_key, environment="us-east1-gcp")
    docsearch = Pinecone.from_existing_index(index_name=PINECONE_INDEX, embedding=base_embeddings)

    ###
    # Run docsearch
    ###
    print("🥞: selecting sources by similarity to query")
    docs = docsearch.similarity_search(query)

    ###
    # Run chain
    ###
    print("🥞: running query against Q&A chain")
    chain = load_qa_with_sources_chain(
        OpenAI(temperature=0,), chain_type="stuff"
    )
    result = chain(
        {"input_documents": docs, "question": query}, return_only_outputs=True
    )
    answer = result["output_text"]

    return answer


@stub.webhook(method="GET", label="ask-fsdl-hook")
def web(query: str, show_sources: bool = True):
    answer = qanda_langchain(query)
    return {
        "answer": answer,
    }


@stub.function(image=image)
def cli(query: str, show_sources: bool = True):
    answer = qanda_langchain(query)
    # Terminal codes for pretty-printing.
    bold, end = "\033[1m", "\033[0m"

    print(f"🦜🥞 {bold}ANSWER:{end}")
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


    interface = gr.Interface(
        fn=qanda_langchain,
        inputs="text",
        outputs="text",
        title="Ask Questions About Deep Learning."
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
