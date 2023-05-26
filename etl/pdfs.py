import modal

import etl.shared

# extend the shared image with PDF-handling dependencies
image = etl.shared.image.pip_install(
    "pypdf~=3.8",
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
def main(json_path="data/llm-papers.json"):
    """Calls the ETL pipeline using a JSON file with PDF metadata.

    modal run etl/pdfs.py --json-path /path/to/json
    """
    import json

    with open(json_path) as f:
        pdf_infos = json.load(f)

    pdf_urls = [pdf["url"] for pdf in pdf_infos]
    pdf_urls = pdf_urls[:1]

    raw_documents = etl.shared.unchunk(
        extract_pdf.map(pdf_urls, return_exceptions=True)
    )

    documents = [json.loads(doc) for doc in raw_documents]

    with etl.shared.stub.run():
        chunked_documents = etl.shared.chunk_into(documents, 10)
        list(etl.shared.add_to_document_db.map(chunked_documents))


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
