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
        modal.Secret.from_name("mongodb-fsdl"),
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

    documents = etl.shared.unchunk(extract_pdf.map(pdf_urls, return_exceptions=True))

    with etl.shared.stub.run():
        chunked_documents = etl.shared.chunk_into(documents, 10)
        list(etl.shared.add_to_document_db.map(chunked_documents))


@stub.function(image=image)
def extract_pdf(pdf_url):
    """Extracts the text from a PDF."""
    from langchain.document_loaders import PyPDFLoader

    loader = PyPDFLoader(pdf_url)
    documents = loader.load_and_split()
    documents = [document.dict() for document in documents]
    for document in documents:  # rename page_content to text
        document["text"] = document["page_content"]
        document.pop("page_content")

    documents = annotate_endmatter(documents)
    for document in documents:
        document["metadata"]["source"] = pdf_url

    documents = etl.shared.enrich_metadata(documents)

    return documents


def annotate_endmatter(pages, min_pages=6):
    """Heuristic for detecting reference sections."""
    out, after_references = [], False
    for idx, page in enumerate(pages):
        content = page["text"].lower()
        if idx >= min_pages and ("references" in content or "bibliography" in content):
            after_references = True
        page["metadata"]["is_endmatter"] = after_references
        out.append(page)
    return out
