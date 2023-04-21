"""Builds a CLI, Webhook, and Gradio app for Q&A on the FSDL corpus.

For details on corpus construction, see the accompanying notebook."""
from fastapi import FastAPI
import modal

# definition of our container image for jobs on Modal
# Modal gets really powerful when you start using multiple images!
image = modal.Image.debian_slim(  # we start from a lightweight linux distro
    python_version="3.10"  # we add a recent Python version
).pip_install(  # and we install the following packages:
    "langchain~=0.0.98",
    # 🦜🔗: a framework for building apps with LLMs
    "openai~=0.26.3",
    # high-quality language models and cheap embeddings
    "tiktoken",
    # tokenizer for OpenAI models
    "pymongo==3.11",
    # python client for MongoDB, our data persistence solution
    "gradio~=3.17",
    # simple web UIs in Python, from 🤗
    "gantry==0.5.6",
    # 🏗️: monitoring, observability, and continual improvement for ML systems
    "pinecone-client",
)

# we define a Stub to hold all the pieces of our app
# most of the rest of this file just adds features onto this Stub
stub = modal.Stub(
    name="ask-fsdl",
    image=image,
    secrets=[
        # this is where we add API keys, passwords, and URLs, which are stored on Modal
        modal.Secret.from_name("pinecone-api-key"),
        modal.Secret.from_name("openai-api-key-fsdl"),
        modal.Secret.from_name("mongodb"),
        modal.Secret.from_name("gantry-api-key"),
    ],
)

PINECONE_INDEX = "openai-ada-fsdl"
MONGO_COLLECTION = "ask-fsdl-llm"

# Terminal codes for pretty-printing.
START, END = "\033[1;38;5;214m", "\033[0m"


@stub.function(image=image, timeout=500)
def sync_vector_db_to_doc_db():
    """Syncs the vector storage onto the document storage."""

    document_client = connect_to_doc_db()
    pretty_log("connected to document DB")

    embedding_engine = get_embedding_engine(allowed_special="all")

    pretty_log("connecting to vector storage")
    vector_index = get_vector_index(PINECONE_INDEX, embedding_engine, delete_all=True)
    pretty_log("connected to vector storage")

    docs = get_documents(document_client, "fsdl")

    pretty_log("splitting into bite-size chunks")
    ids, texts, metadatas = prep_documents_for_vector_storage(docs)

    pretty_log(f"sending to vector store {PINECONE_INDEX}")
    add_to_vector_storage(texts, metadatas, vector_index, ids=ids)


def qanda_langchain(query: str, request_id=None, with_logging=False) -> str:
    """Runs sourced Q&A for a query using LangChain.

    Arguments:
        query: The query to run Q&A on.
        request_id: A unique identifier for the request.
        with_logging: If True, logs the interaction to Gantry.
    """
    from langchain.chains.qa_with_sources import load_qa_with_sources_chain
    from langchain.llms import OpenAI

    embedding_engine = get_embedding_engine(allowed_special="all")

    pretty_log("connecting to vector storage")
    vector_index = get_vector_index(PINECONE_INDEX, embedding_engine, delete_all=False)
    pretty_log("connected to vector storage")

    pretty_log(f"running on query: {query}")
    pretty_log("selecting sources by similarity to query")
    sources = vector_index.similarity_search(query, k=5)

    pretty_log("SOURCES")
    print(*[source.page_content for source in sources], sep="\n\n---\n\n")

    pretty_log("running query against Q&A chain")

    llm = OpenAI("text-davinci-003", temperature=0)
    chain = load_qa_with_sources_chain(llm, chain_type="stuff")

    result = chain(
        {"input_documents": sources, "question": query}, return_only_outputs=True
    )
    answer = result["output_text"]

    print(answer)

    if with_logging:
        pretty_log("logging results to gantry")
        record_key = log_event(query, sources, answer, request_id=request_id)
        pretty_log(f"logged to gantry with key {record_key}")

    return answer


def log_event(query, sources, answer, request_id=None):
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


def get_embedding_engine(model="text-embedding-ada-002", **kwargs):
    from langchain.embeddings import OpenAIEmbeddings

    embedding_engine = OpenAIEmbeddings(model="text-embedding-ada-002", **kwargs)

    return embedding_engine


def connect_to_doc_db():
    import os
    import pymongo

    mongodb_password = os.environ["MONGODB_PASSWORD"]
    mongodb_uri = os.environ["MONGODB_URI"]
    connection_string = f"mongodb+srv://fsdl:{mongodb_password}@{mongodb_uri}/?retryWrites=true&w=majority"
    client = pymongo.MongoClient(connection_string)
    return client


def get_documents(client, db="fsdl", collection=MONGO_COLLECTION):
    """Fetches a collection of documents from a document database."""
    db = client.get_database(db)
    collection = db.get_collection(collection)
    docs = collection.find({"metadata.ignore": False})

    return docs


def get_vector_index(index_name, embedding_engine, delete_all=True):
    """Returns a vector index that offers similarity search."""
    import os

    import langchain
    import pinecone

    pinecone_api_key = os.environ["PINECONE_API_KEY"]
    pinecone.init(api_key=pinecone_api_key, environment="us-east1-gcp")

    # use pinecone SDK to connect to an index or create a new one if it doesn't exist
    try:
        index = pinecone.Index(PINECONE_INDEX)
        if delete_all:  # optionally, wipe it clean
            index.delete(delete_all=True)
            pretty_log("existing index wiped")
    except pinecone.core.client.exceptions.NotFoundException:
        pretty_log("creating vector index")
        pinecone.create_index(
            name=PINECONE_INDEX, dimension=1536, metric="cosine", pod_type="p1.x1"
        )
        pretty_log("vector index created")

    # now, wrap that index in LangChain vector store
    index = langchain.vectorstores.Pinecone.from_existing_index(
        index_name=index_name, embedding=embedding_engine
    )

    return index


def add_to_vector_storage(texts, metadatas, vector_index, **kwargs):
    vector_index.add_texts(texts, metadatas=metadatas, **kwargs)


def prep_documents_for_vector_storage(documents):
    """Prepare documents from document store for embedding and vector storage.

    Documents are split into chunks so that they can be used with sourced Q&A.

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


@stub.function(image=image)
@modal.web_endpoint(method="GET", label="ask-fsdl-hook")
def web(query: str, request_id=None):
    pretty_log(
        f"handling request with client-provided id: {request_id}"
    ) if request_id else None
    answer = qanda_langchain(query, request_id=request_id, with_logging=True)
    return {
        "answer": answer,
    }


@stub.function(image=image)
def cli(query: str):
    answer = qanda_langchain(query)
    pretty_log("🦜 ANSWER 🦜")
    print(answer)


web_app = FastAPI()


@web_app.get("/")
async def root():
    return {"message": "Hello World"}


# Wrap in a Gradio interface for debugging backend
@stub.function(image=image)
@modal.asgi_app(label="ask-fsdl")
def fastapi_app():
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
        ],
        allow_flagging="never",
    )

    return mount_gradio_app(app=web_app, blocks=interface, path="/gradio")


# Add a debugging access point on Modal
@stub.function(image=image, interactive=True)
def debug():
    import IPython

    IPython.embed()


def pretty_log(str):
    print(f"{START}🥞: {str}{END}")
