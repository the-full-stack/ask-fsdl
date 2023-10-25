import modal

from app import vecstore
from app.utils import pretty_log

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
    name="askfsdl-test-queries",
    image=image,
    secrets=[
        modal.Secret.from_name("openai-api-key-fsdl"),
        modal.Secret.from_name("wandb-api-key-fsdl"),
    ],
    mounts=[modal.Mount.from_local_python_packages("app.vecstore", "app.utils")],
)


@stub.local_entrypoint()
def run_query_experiment(jsonl_path="data/queries.jsonl"):
    """Run sample queries through the vector index and log the results."""
    import json

    # load example queries
    with open(jsonl_path) as f:
        queries = [json.loads(line) for line in f.readlines()]

    _run_query_experiment.remote(queries)


@stub.function()
def _run_query_experiment(queries):
    # run retrieval on them
    queries_results = query_vector_index.map([example["query"] for example in queries])

    # log the results
    log_query_results(queries_results, queries)


@stub.function(
    network_file_systems={
        str(VECTOR_DIR): vector_storage,
    },
    concurrency_limit=10,
)
def query_vector_index(query, k=10):
    """Query the vector index for documents similar to the query."""
    embedding_engine = vecstore.get_embedding_engine(allowed_special="all")

    vector_index = vecstore.connect_to_vector_index(
        vecstore.INDEX_NAME, embedding_engine
    )

    sources_and_scores = vector_index.similarity_search_with_score(query, k=k)

    return sources_and_scores


def log_query_results(queries_results, queries):
    """Log the query results to Weights & Biases."""
    import wandb

    wandb.login()

    pretty_log("constructing query dataframe")
    queries_df = construct_queries_df(queries_results, queries)

    with wandb.init(project="askfsdl-test-queries") as run:
        run.log({"queries": queries_df})


def construct_queries_df(queries_results, queries):
    """Construct a dataframe of overall results from individual results"""
    import pandas as pd

    per_query_dfs = [
        construct_query_df(query_results, query)
        for query_results, query in zip(queries_results, queries)
    ]
    return pd.concat(per_query_dfs)


def construct_query_df(query_results, query):
    """Create a dataframe with results and metadata for a single query."""
    import pandas as pd

    documents, scores = zip(*query_results)
    texts = [document.page_content for document in documents]
    metadatas = [document.metadata for document in documents]

    df = pd.DataFrame({"texts": texts, "scores": scores})
    df = add_metadata(df, metadatas)
    df["query"] = query["query"]
    df["relevance"] = query["relevance"]

    return df


def add_metadata(df, metadatas):
    for idx, metadata in enumerate(metadatas):
        for key, value in metadata.items():
            df.loc[idx, key] = value
    return df
