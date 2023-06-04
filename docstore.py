"""Functions to connect to a document database and fetch documents from it."""
MONGO_DATABASE = "fsdl"
MONGO_COLLECTION = "ask-fsdl"


def get_documents(client, db=MONGO_DATABASE, collection=MONGO_COLLECTION):
    """Fetches a collection of documents from a document database."""
    db = client.get_database(db)
    collection = db.get_collection(collection)
    docs = collection.find({"metadata.ignore": False})

    return docs


def connect():
    """Connects to a document database, here MongoDB."""
    import os

    import pymongo

    mongodb_user = os.environ["MONGODB_USER"]
    mongodb_password = os.environ["MONGODB_PASSWORD"]
    mongodb_uri = os.environ["MONGODB_URI"]

    connection_string = f"mongodb+srv://{mongodb_user}:{mongodb_password}@{mongodb_uri}/?retryWrites=true&w=majority"
    client = pymongo.MongoClient(connection_string)

    return client


def flush():
    client = connect()

    db = client.get_database(MONGO_DATABASE)
    collection = db.get_collection(MONGO_COLLECTION)
    collection.drop()
