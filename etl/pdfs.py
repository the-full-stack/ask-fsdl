import modal

import etl.shared

# extend the shared image with PDF-handling dependencies
image = etl.shared.image.pip_install(
    "arxiv~=1.4",
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
    import arxiv

    from langchain.document_loaders import PyPDFLoader

    loader = PyPDFLoader(pdf_url)

    documents = loader.load_and_split()
    documents = [document.dict() for document in documents]
    for document in documents:  # rename page_content to text
        document["text"] = document["page_content"]
        document.pop("page_content")

    if "arxiv" in pdf_url:
        arxiv_id = extract_arxiv_id_from_url(pdf_url)
        result = next(arxiv.Search(id_list=[arxiv_id], max_results=1).results())
        arxiv_metadata = {
            "arxiv_id": arxiv_id,
            "title": result.title,
            "date": result.updated,
        }
    else:
        arxiv_metadata = {}

    documents = annotate_endmatter(documents)
    for document in documents:
        document["metadata"]["source"] = pdf_url
        document["metadata"] |= arxiv_metadata
        title, page = (
            document["metadata"].get("title", None),
            document["metadata"]["page"],
        )
        if title:
            document["metadata"]["full-title"] = f"{title} - p{page}"

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


def extract_arxiv_id_from_url(url):
    import re

    # pattern = r"(?:arxiv\.org/abs/|arxiv\.org/pdf/)(\d{4}\.\d{4,5}(?:v\d+)?)"
    match_arxiv_url = r"(?:arxiv\.org/abs/|arxiv\.org/pdf/)"
    match_id = r"(\d{4}\.\d{4,5}(?:v\d+)?)"  # 4 digits, a dot, and 4 or 5 digits
    optional_version = r"(?:v\d+)?"

    pattern = match_arxiv_url + match_id + optional_version

    match = re.search(pattern, url)
    if match:
        return match.group(1)
    else:
        return None
