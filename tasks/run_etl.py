import argparse
import os
import subprocess


def pretty_log(message):
    print(f"== {message} ==")


def modal_run(task, json_path, db, collection):
    pretty_log(f"Extracting {task}")
    subprocess.run(
        [
            "modal",
            "run",
            f"etl/{task}.py",
            "--json-path",
            json_path,
            "--db",
            db,
            "--collection",
            collection,
        ]
    )


def drop_collection(db, collection):
    pretty_log(f"Dropping collection {collection} in {db}")
    subprocess.run(
        ["modal", "run", "app.py::drop_docs", "--db", db, "--collection", collection]
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--drop",
        action="store_true",
        help="If set, the collection will be dropped before running the tasks",
    )
    parser.add_argument(
        "--db",
        default=os.environ.get("MONGODB_DATABASE"),
        help="Name of the database. Default is the value of the MONGODB_DATABASE environment variable",
    )
    parser.add_argument(
        "--collection",
        default=os.environ.get("MONGODB_COLLECTION"),
        help="Name of the collection. Default is the value of the MONGODB_COLLECTION environment variable",
    )

    args = parser.parse_args()

    if args.drop:
        drop_collection(args.db, args.collection)

    modal_run("videos", "data/videos.json", args.db, args.collection)
    modal_run("markdown", "data/lectures-2022.json", args.db, args.collection)
    modal_run("pdfs", "data/llm-papers.json", args.db, args.collection)


if __name__ == "__main__":
    main()
