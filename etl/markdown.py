import modal

# definition of our container image and app for deployment on Modal
# see app.py for more details
image = modal.Image.debian_slim(python_version="3.10").pip_install(
    "langchain~=0.0.98",
    "mistune",
    "python-slugify",
    "pymongo[srv]==3.11",
)

stub = modal.Stub(
    name="etl-markdown",
    image=image,
    secrets=[
        modal.Secret.from_name("mongodb"),
    ],
    mounts=[
        # we make our local modules available to the container
        *modal.create_package_mounts(module_names=["docstore", "utils"])
    ],
)


@stub.local_entrypoint()
def main(json_path="data/markdown.json"):
    """Calls the ETL pipeline using a JSON file with markdown file metadata.

    modal run etl/markdown.py --json-path /path/to/json
    """
    import json

    with open(json_path) as f:
        markdown_corpus = json.load(f)

    website_url, md_url = (
        markdown_corpus["website_url_base"],
        markdown_corpus["md_url_base"],
    )

    lectures = markdown_corpus["lectures"]

    documents = [  # each lecture creates multiple documents, so we flatten
        document
        for lecture_documents in to_documents.map(
            lectures, kwargs={"website_url": website_url, "md_url": md_url}
        )
        for document in lecture_documents
    ]

    # split up documents into 10 batches to reduce number of connections
    add_to_document_db.map(chunk_into(documents, n_chunks=10))

    return documents


@stub.function(image=image)
def to_documents(lecture, website_url, md_url):
    title, title_slug = lecture["title"], lecture["slug"]
    markdown_url = f"{md_url}/{title_slug}/index.md"
    website_url = f"{website_url}/{title_slug}"

    text = get_text_from(markdown_url)
    headings, heading_slugs = get_target_headings_and_slugs(text)

    subtexts = split_by_headings(text, headings)
    headings, heading_slugs = [""] + headings, [""] + heading_slugs

    sources = [f"{website_url}#{heading}" for heading in heading_slugs]
    metadatas = [
        {"source": source, "heading": heading, "title": title}
        for heading, source in zip(headings, sources)
    ]

    documents = [
        {"text": subtext, "metadata": metadata}
        for subtext, metadata in zip(subtexts, metadatas)
    ]

    return documents


@stub.function(image=image)
def get_text_from(url):
    from smart_open import open

    with open(url) as f:
        contents = f.read()
    return contents


@stub.function(image=image)
def get_target_headings_and_slugs(text):
    """Pull out headings from a markdown document and slugify them."""
    import mistune
    from slugify import slugify

    markdown_parser = mistune.create_markdown(renderer="ast")
    parsed_text = markdown_parser(text)

    heading_objects = [obj for obj in parsed_text if obj["type"] == "heading"]
    h2_objects = [obj for obj in heading_objects if obj["level"] == 2]

    targets = [
        obj
        for obj in h2_objects
        if not (obj["children"][0]["text"].startswith("description: "))
    ]
    target_headings = [tgt["children"][0]["text"] for tgt in targets]

    heading_slugs = [slugify(target_heading) for target_heading in target_headings]

    return target_headings, heading_slugs


# TODO: unify across ETLs
@stub.function(image=image)
def add_to_document_db(documents_json):
    """Adds a collection of json documents to a document database."""
    from pymongo import InsertOne

    import docstore

    client = docstore.connect()

    db = client.get_database(docstore.MONGO_DATABASE)
    collection = db.get_collection(docstore.MONGO_COLLECTION)

    requesting, CHUNK_SIZE = [], 250

    for document in documents_json:
        requesting.append(InsertOne(document))

        if len(requesting) >= CHUNK_SIZE:
            collection.bulk_write(requesting)
            requesting = []

    if requesting:
        collection.bulk_write(requesting)


def chunk_into(list, n_chunks):
    """Splits list into n_chunks pieces, non-contiguously."""
    for ii in range(0, n_chunks):
        yield list[ii::n_chunks]


def split_by_headings(text, headings):
    """Separate Markdown text by level-1 headings."""
    texts = []
    for heading in reversed(headings):
        text, section = text.split("# " + heading)
        texts.append(f"## {heading}{section}")
    texts.append(text)
    texts = list(reversed(texts))
    return texts


def enrich_metadata(pages):
    """Add our metadata: sha256 hash and ignore flag."""
    import hashlib

    for page in pages:
        m = hashlib.sha256()
        m.update(page.page_content.encode("utf-8"))
        page.metadata["sha256"] = m.hexdigest()
        page.metadata["ignore"] = False
    return pages
