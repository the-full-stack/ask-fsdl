import modal

# definition of our container image and app for deployment on Modal
# see app.py for more details
image = modal.Image.debian_slim(python_version="3.10").pip_install(
    "langchain~=0.0.98",
    "pypdf~=3.8",
    "pymongo[srv]==3.11",
)

stub = modal.Stub(
    name="etl-pdfs",
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
def main(json_path="data/papers.json"):
    """Calls the ETL pipeline using a JSON file with PDF metadata.

    modal run etl.py --json-path /path/to/json
    """
    import json

    with open(json_path) as f:
        pdf_infos = json.load(f)

    pdf_urls = [pdf["url"] for pdf in pdf_infos]

    results = list(extract_pdf.map(pdf_urls, return_exceptions=True))
    add_to_document_db.call(results)


@stub.function(image=image)
def flush_doc_db():
    """Empties the document database."""
    import docstore

    docstore.flush()


@stub.function(image=image)
def extract_pdf(pdf_url):
    """Creates a LangChain document for a PDF and serializes it to JSON."""
    from langchain.document_loaders import PyPDFLoader

    loader = PyPDFLoader(pdf_url)
    pages = loader.load_and_split()

    for page in pages:
        page.metadata["source"] = pdf_url

    pages = enrich_metadata(pages)

    return [page.json() for page in pages]


@stub.function(image=image)
def add_to_document_db(all_pages_jsons):
    """Adds a collection of documents to a document database."""
    from langchain.docstore.document import Document
    from pymongo import InsertOne

    import docstore

    client = docstore.connect()

    db = client.get_database("fsdl")
    collection = db.get_collection(docstore.MONGO_COLLECTION)

    all_pages = []
    for pages_json in all_pages_jsons:
        pages = [Document.parse_raw(page) for page in pages_json]
        if len(pages) >= 75:
            # TODO: move this earlier in the processing, keep first 75 pages
            continue
        all_pages += pages

    requesting, CHUNK_SIZE = [], 250

    for page in all_pages:
        metadata = page.metadata
        document = {"text": page.page_content, "metadata": metadata}
        requesting.append(InsertOne(document))

        if len(requesting) >= CHUNK_SIZE:
            collection.bulk_write(requesting)
            requesting = []

    if requesting:
        collection.bulk_write(requesting)


def annotate_endmatter(pages, min_pages=6):
    """Heuristic for detecting reference sections.""" ""
    out, after_references = [], False
    for idx, page in enumerate(pages):
        content = page.page_content.lower()
        if idx >= min_pages and ("references" in content or "bibliography" in content):
            after_references = True
        page.metadata["is_endmatter"] = after_references
        out.append(page)
    return out


def enrich_metadata(pages):
    """Add our metadata: sha256 hash and ignore flag."""
    import hashlib

    pages = annotate_endmatter(pages)
    for page in pages:
        m = hashlib.sha256()
        m.update(page.page_content.encode("utf-8"))
        page.metadata["sha256"] = m.hexdigest()
        if page.metadata.get("is_endmatter"):
            page.metadata["ignore"] = True
        else:
            page.metadata["ignore"] = False
    return pages
