"""Utilities for creating and using vector indexes."""
from pathlib import Path
from typing import List
from utils import pretty_log

INDEX_NAME = "openai-ada-fsdl"
VECTOR_DIR = Path("/vectors")


def connect_to_vector_index(index_name: str, embedding_engine) -> 'FAISS':
    """Adds the texts and metadatas to the vector index."""
    from langchain.vectorstores import FAISS

    try:
        vector_index = FAISS.load_local(VECTOR_DIR, embedding_engine, index_name)
        return vector_index
    except Exception as e:
        pretty_log(f"Error connecting to vector index: {e}")
        return None


def get_embedding_engine(model: str = "text-embedding-ada-002", **kwargs) -> 'OpenAIEmbeddings':
    """Retrieves the embedding engine."""
    from langchain.embeddings import OpenAIEmbeddings

    try:
        embedding_engine = OpenAIEmbeddings(model=model, **kwargs)
        return embedding_engine
    except Exception as e:
        pretty_log(f"Error initializing embedding engine: {e}")
        return None


def create_vector_index(index_name: str, embedding_engine, documents: List[str], metadatas: List[dict]) -> 'FAISS':
    """Creates a vector index that offers similarity search."""
    from langchain.vectorstores import FAISS

    # Clean up existing index files if any
    files = list(VECTOR_DIR.glob(f"{index_name}.*"))
    if files:
        for file in files:
            try:
                file.unlink()
                pretty_log(f"Deleted existing index file: {file.name}")
            except Exception as e:
                pretty_log(f"Error deleting file {file.name}: {e}")

    # Create a new index
    try:
        index = FAISS.from_texts(
            texts=documents, embedding=embedding_engine, metadatas=metadatas
        )
        return index
    except Exception as e:
        pretty_log(f"Error creating vector index: {e}")
        return None
