"""Utilities for creating and using vector indexes."""
from pathlib import Path

from .utils import pretty_log

INDEX_NAME = "openai-ada-fsdl"
VECTOR_DIR = Path("/vectors")


def connect_to_vector_index(index_name, embedding_engine):
    """Adds the texts and metadatas to the vector index."""
    from langchain.vectorstores import FAISS

    vector_index = FAISS.load_local(VECTOR_DIR, embedding_engine, index_name)

    return vector_index


def get_embedding_engine(model="text-embedding-ada-002", **kwargs):
    """Retrieves the embedding engine."""
    from langchain.embeddings import OpenAIEmbeddings

    embedding_engine = OpenAIEmbeddings(model=model, **kwargs)

    return embedding_engine


def create_vector_index(index_name, embedding_engine, documents, metadatas):
    """Creates a vector index that offers similarity search."""
    from langchain import FAISS

    files = VECTOR_DIR.glob(f"{index_name}.*")
    if files:
        for file in files:
            file.unlink()
        pretty_log("existing index wiped")

    index = FAISS.from_texts(
        texts=documents, embedding=embedding_engine, metadatas=metadatas
    )

    return index
