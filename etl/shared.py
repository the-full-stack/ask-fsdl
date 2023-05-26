import modal

# definition of our container image and app for deployment on Modal
# see app.py for more details
image = modal.Image.debian_slim(python_version="3.10").pip_install(
    "langchain~=0.0.98",
    "pymongo[srv]==3.11",
)

stub = modal.Stub(
    name="etl-shared",
    secrets=[
        modal.Secret.from_name("mongodb"),
    ],
    mounts=[*modal.create_package_mounts(module_names=["docstore", "utils"])],
)


@stub.function(image=image)
def flush_doc_db():
    """Empties the document database."""
    import docstore

    docstore.flush()


@stub.function(image=image)
def add_to_document_db(documents_json, db=None, collection=None):
    """Adds a collection of json documents to a document database."""

    from pymongo import InsertOne

    import docstore

    client = docstore.connect()

    db = client.get_database(db if db else docstore.MONGO_DATABASE)
    collection = db.get_collection(
        collection if collection else docstore.MONGO_COLLECTION
    )

    requesting, CHUNK_SIZE = [], 250

    for document in documents_json:
        requesting.append(InsertOne(document))

        if len(requesting) >= CHUNK_SIZE:
            collection.bulk_write(requesting)
            requesting = []

    if requesting:
        collection.bulk_write(requesting)


@stub.function(image=image)
def query_document_db(query, projection=None, db=None, collection=None):
    """Runs a query against the document db and returns a list of results."""
    import docstore

    client = docstore.connect()

    db = client.get_database(db if db else docstore.MONGO_DATABASE)
    collection = db.get_collection(
        collection if collection else docstore.MONGO_COLLECTION
    )

    return list(collection.find(query, projection))


@stub.function(image=image)
def query_one_document_db(query, projection=None, db=None, collection=None):
    """Runs a query against the document db and returns the first result."""
    import docstore

    client = docstore.connect()

    db = client.get_database(db if db else docstore.MONGO_DATABASE)
    collection = db.get_collection(
        collection if collection else docstore.MONGO_COLLECTION
    )

    return collection.find_one(query, projection)


def chunk_into(list, n_chunks):
    """Splits list into n_chunks pieces, non-contiguously."""
    for ii in range(0, n_chunks):
        yield list[ii::n_chunks]


def unchunk(list_of_lists):
    """Recombines a list of lists into a single list."""
    return [item for sublist in list_of_lists for item in sublist]


def display_modal_image(image):
    """Display a modal.Image cleanly in a Jupyter notebook."""
    from IPython.display import HTML
    from pygments import highlight
    from pygments.formatters import HtmlFormatter
    from pygments.lexers import get_lexer_by_name

    dockerfile_commands = get_image_dockerfile_commands(image)

    fmt = HtmlFormatter(style="rrt", cssclass="_pygments_code", nobackground=False)
    css_styles = fmt.get_style_defs(".output_html")

    lexer = get_lexer_by_name("docker")
    html = highlight("\n".join(dockerfile_commands), lexer, fmt)

    html = f"<style>{css_styles}</style><h1><code>modal.Image</code></h1>{html}"

    return HTML(html)


def get_image_dockerfile_commands(image):
    """Workaround for unavailability of dockerfile commands in modal.Image objects."""
    image_description = str(image)

    # dockerfile commands appear as a stringified Python list like below
    # Image(['CMD list', "FROM the modal image"])
    dockerfile_commands_list_str = image_description[len("Image([") : -len("])")]

    # we "unstringify" the list of strings before returning it
    dockerfile_commands = dockerfile_commands_list_str.split(", ")
    dockerfile_commands = [cmd.strip("'").strip('"') for cmd in dockerfile_commands]

    return dockerfile_commands
