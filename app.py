import modal
from fastapi import FastAPI
from fastapi.responses import RedirectResponse

import vecstore
from utils import pretty_log

# Definition of our container image for jobs on Modal
image = modal.Image.debian_slim(
    python_version="3.10"
).pip_install(
    "langchain==0.0.184",
    "openai~=0.27.7",
    "tiktoken",
    "faiss-cpu",
    "pymongo[srv]==3.11",
    "gradio~=3.34",
    "gantry==0.5.6",
)

# Define a Stub to hold all the pieces of our app
stub = modal.Stub(
    name="askfsdl-backend",
    image=image,
    secrets=[
        modal.Secret.from_name("mongodb-fsdl"),
        modal.Secret.from_name("openai-api-key-fsdl"),
        modal.Secret.from_name("gantry-api-key-fsdl"),
    ],
    mounts=[
        modal.Mount.from_local_python_packages(
            "vecstore", "docstore", "utils", "prompts"
        )
    ],
)

VECTOR_DIR = vecstore.VECTOR_DIR
vector_storage = modal.NetworkFileSystem.persisted("vector-vol")


@stub.function(
    image=image,
    network_file_systems={str(VECTOR_DIR): vector_storage},
)
@modal.web_endpoint(method="GET")
def web(query: str, request_id=None):
    """Exposes our Q&A chain for queries via a web endpoint."""
    import os

    if request_id:
        pretty_log(f"Handling request with client-provided id: {request_id}")

    answer = qanda.remote(
        query,
        request_id=request_id,
        with_logging=bool(os.environ.get("GANTRY_API_KEY")),
    )
    return {"answer": answer}


@stub.function(
    image=image,
    network_file_systems={str(VECTOR_DIR): vector_storage},
    keep_warm=1,
)
def qanda(query: str, request_id=None, with_logging: bool = False) -> str:
    """Runs sourced Q&A for a query using LangChain."""
    from langchain.chains.qa_with_sources import load_qa_with_sources_chain
    from langchain.chat_models import ChatOpenAI

    import prompts
    import vecstore

    embedding_engine = vecstore.get_embedding_engine(allowed_special="all")

    pretty_log("Connecting to vector storage")
    vector_index = vecstore.connect_to_vector_index(
        vecstore.INDEX_NAME, embedding_engine
    )
    pretty_log("Connected to vector storage")
    pretty_log(f"Found {vector_index.index.ntotal} vectors to search over")

    pretty_log(f"Running on query: {query}")
    pretty_log("Selecting sources by similarity to query")
    sources_and_scores = vector_index.similarity_search_with_score(query, k=3)

    sources, scores = zip(*sources_and_scores)

    pretty_log("Running query against Q&A chain")

    llm = ChatOpenAI(model_name="gpt-4", temperature=0, max_tokens=256)
    chain = load_qa_with_sources_chain(
        llm,
        chain_type="stuff",
        verbose=with_logging,
        prompt=prompts.main,
        document_variable_name="sources",
    )

    result = chain(
        {"input_documents": sources, "question": query}, return_only_outputs=True
    )
    answer = result["output_text"]

    if with_logging:
        print(answer)
        pretty_log("Logging results to Gantry")
        record_key = log_event(query, sources, answer, request_id=request_id)
        if record_key:
            pretty_log(f"Logged to Gantry with key {record_key}")

    return answer


@stub.function(
    image=image,
    network_file_systems={str(VECTOR_DIR): vector_storage},
    cpu=8.0,
)
def create_vector_index(collection: str = None, db: str = None):
    """Creates a vector index for a collection in the document database."""
    import docstore

    pretty_log("Connecting to document store")
    db = docstore.get_database(db)
    pretty_log(f"Connected to database {db.name}")

    collection = docstore.get_collection(collection, db)
    pretty_log(f"Collecting documents from {collection.name}")
    docs = docstore.get_documents(collection, db)

    pretty_log("Splitting into bite-size chunks")
    ids, texts, metadatas = prep_documents_for_vector_storage(docs)

    pretty_log(f"Sending to vector index {vecstore.INDEX_NAME}")
    embedding_engine = vecstore.get_embedding_engine(disallowed_special=())
    vector_index =
