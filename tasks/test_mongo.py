# test_mongo.py
from dotenv import load_dotenv
import pytest
import pymongo
import os

from run_etl import (
    modal_run,
    drop_collection,
)


# setup fixture for MongoDB connection
@pytest.fixture(scope="module")
def mongodb_connection():
    dotenv_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    load_dotenv(dotenv_path)
    db_name = os.environ.get("MONGODB_DATABASE")
    collection_name = os.environ.get("MONGODB_COLLECTION")
    mongo_user = os.environ.get("MONGODB_USER")
    mongo_password = os.environ.get("MONGODB_PASSWORD")
    mongo_uri = os.environ.get("MONGODB_URI")
    mongo_uri_template = "mongodb+srv://<user>:<password>@<db_uri>/"

    # Replace placeholders with actual values
    mongo_uri = (
        mongo_uri_template.replace("<user>", mongo_user)
        .replace("<password>", mongo_password)
        .replace("<db_uri>", mongo_uri)
    )

    client = pymongo.MongoClient(mongo_uri)
    db = client[db_name]
    collection = db[collection_name]

    yield collection  # provides a collection to each test where it's used

    client.close()


def test_mongo_connection(mongodb_connection):
    assert mongodb_connection is not None, "MongoDB connection failed"


def test_mongo_permissions(mongodb_connection):
    try:
        mongodb_connection.insert_one({"test_key": "test_value"})
        mongodb_connection.delete_one({"test_key": "test_value"})
    except Exception as e:
        pytest.fail(f"MongoDB permission test failed with error: {str(e)}")


def test_modal_run(mongodb_connection):
    db_name = os.environ.get("MONGODB_DATABASE")
    collection_name = os.environ.get("MONGODB_COLLECTION")

    try:
        modal_run("videos", "data/videos.json", db_name, collection_name)
    except Exception as e:
        pytest.fail(f"modal_run failed with error: {str(e)}")


def test_drop_collection(mongodb_connection):
    db_name = os.environ.get("MONGODB_DATABASE")
    collection_name = os.environ.get("MONGODB_COLLECTION")

    try:
        drop_collection(db_name, collection_name)
    except Exception as e:
        pytest.fail(f"drop_collection failed with error: {str(e)}")
