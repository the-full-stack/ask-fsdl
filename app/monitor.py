import modal

from . import vecstore
from .utils import pretty_log


WANDB_EXPERIMENT = "askfsdl-embeddings"
MAX_EMBEDDING_DIM = 128
MAX_EMBEDDING_COUNT = 5_000

VECTOR_DIR = vecstore.VECTOR_DIR
vector_storage = modal.NetworkFileSystem.persisted("vector-vol")

image = modal.Image.debian_slim(python_version="3.10").pip_install(
    "langchain==0.0.321",
    "langsmith==0.0.49",
    "openai~=0.27.7",
    "pandas==1.5.3",
    "faiss-cpu",
    "tiktoken",
    "wandb==0.15.12",
)

stub = modal.Stub(
    name="askfsdl-monitor",
    image=image,
    secrets=[
        modal.Secret.from_name("openai-api-key-fsdl"),
        modal.Secret.from_name("wandb-api-key-fsdl"),
    ],
    mounts=[modal.Mount.from_local_python_packages("app.vecstore", "app.utils")],
)


@stub.function(
    schedule=modal.Cron("17 1 * * 4"),
    network_file_systems={
        str(VECTOR_DIR): vector_storage,
    },
)
def log_vector_index():
    """Log the contents of the vector index to Weights & Biases."""
    import wandb

    wandb.login()

    embedding_engine = vecstore.get_embedding_engine(allowed_special="all")

    pretty_log("connecting to vector storage")
    vector_index = vecstore.connect_to_vector_index(
        vecstore.INDEX_NAME, embedding_engine
    )
    pretty_log("connected to vector storage")

    pretty_log("constructing embedding dataframe")

    cfg = {
        "MAX_EMBEDDING_DIM": MAX_EMBEDDING_DIM,
        "MAX_EMBEDDING_COUNT": MAX_EMBEDDING_COUNT,
        "index_name": vecstore.INDEX_NAME,
        "embedding_engine": embedding_engine.dict(exclude={"openai_api_key"}),
    }

    with wandb.init(project=WANDB_EXPERIMENT, config=cfg) as run:
        embeddings_df = extract_embeddings_df(vector_index)
        run.log(
            {
                "embeddings": embeddings_df.sample(n=MAX_EMBEDDING_COUNT)
                if len(embeddings_df) > MAX_EMBEDDING_COUNT
                else embeddings_df
            }
        )


def extract_embeddings_df(vector_index):
    """Construct a dataframe of embeddings from the vector index."""
    texts, metadatas, vectors = scan_vector_index(vector_index)

    embeddings_df = build_embeddings_df(texts, metadatas, vectors)

    return embeddings_df


def scan_vector_index(vector_index):
    """Retrieve all texts, metadata, and vectors from the vector index."""
    number_of_vectors, dim = vector_index.index.ntotal, vector_index.index.d

    logged_dim = min(MAX_EMBEDDING_DIM, dim)
    texts, metadatas, vectors = [], [], []

    for index_id in range(number_of_vectors):
        vector = vector_index.index.reconstruct_n(index_id, 1)[0]
        vectors.append(vector[:logged_dim])
        document = vector_index.docstore.search(
            vector_index.index_to_docstore_id[index_id]
        )
        text, metadata = document.page_content, document.metadata
        texts.append(text), metadatas.append(metadata)

    return texts, metadatas, vectors


def build_embeddings_df(texts, metadatas, vectors):
    """Construct a dataframe of embeddings from the vector index."""
    import pandas as pd

    df = pd.DataFrame({"text": texts, "embedding": vectors})
    df = add_metadata(df, metadatas)

    df["is_youtube"] = df["source"].apply(lambda s: "youtube.com" in s)
    df["is_paper"] = df["source"].apply(lambda s: (".pdf" in s or "arxiv.org" in s))
    df["is_lecture"] = df["source"].apply(lambda s: "fullstackdeeplearning.com" in s)

    def guess_source(row):
        if row["is_youtube"]:
            return "youtube"
        elif row["is_paper"]:
            return "paper"
        elif row["is_lecture"]:
            return "fsdl"

    df["source_type"] = df.apply(guess_source, axis=1)

    return df


def add_metadata(df, metadatas):
    for idx, metadata in enumerate(metadatas):
        for key, value in metadata.items():
            df.loc[idx, key] = value
    return df
