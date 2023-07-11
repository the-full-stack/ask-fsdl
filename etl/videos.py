import modal

import etl.shared

# extend the shared image with YouTube-handling dependencies
image = etl.shared.image.pip_install("youtube-transcript-api==0.6.1", "srt==3.5.3")

stub = modal.Stub(
    name="etl-videos",
    image=image,
    secrets=[
        modal.Secret.from_name("mongodb-fsdl"),
    ],
    mounts=[
        # we make our local modules available to the container
        modal.Mount.from_local_python_packages("docstore", "utils")
    ],
)


@stub.local_entrypoint()
def main(json_path="data/videos.json", collection=None, db=None):
    """Calls the ETL pipeline using a JSON file with YouTube video metadata.

    modal run etl/videos.py --json-path /path/to/json
    """
    import json

    with open(json_path) as f:
        video_infos = json.load(f)

    documents = (
        etl.shared.unchunk(  # each video creates multiple documents, so we flatten
            extract_subtitles.map(video_infos, return_exceptions=True)
        )
    )

    with etl.shared.stub.run():
        chunked_documents = etl.shared.chunk_into(documents, 10)
        list(
            etl.shared.add_to_document_db.map(
                chunked_documents, kwargs={"db": db, "collection": collection}
            )
        )


@stub.function(
    retries=modal.Retries(max_retries=3, backoff_coefficient=2.0, initial_delay=5.0)
)
def extract_subtitles(video_info):
    video_id, video_title = video_info["id"], video_info["title"]
    subtitles = get_transcript(video_id)
    chapters = get_chapters(video_id)
    chapters = add_transcript(chapters, subtitles)

    documents = create_documents(chapters, video_id, video_title)

    return documents


def get_transcript(video_id):
    from youtube_transcript_api import YouTubeTranscriptApi

    return YouTubeTranscriptApi.get_transcript(video_id)


def get_chapters(video_id):
    import requests

    base_url = "https://yt.lemnoslife.com"
    request_path = "/videos"

    params = {"id": video_id, "part": "chapters"}

    response = requests.get(base_url + request_path, params=params)
    response.raise_for_status()

    chapters = response.json()["items"][0]["chapters"]["chapters"]
    assert len(chapters) >= 0, "Video has no chapters"

    for chapter in chapters:
        del chapter["thumbnails"]

    return chapters


def add_transcript(chapters, subtitles):
    for ii, chapter in enumerate(chapters):
        next_chapter = chapters[ii + 1] if ii < len(chapters) - 1 else {"time": 1e10}

        text = " ".join(
            [
                seg["text"]
                for seg in subtitles
                if seg["start"] >= chapter["time"]
                and seg["start"] < next_chapter["time"]
            ]
        )

        chapter["text"] = text

    return chapters


def create_documents(chapters, id, video_title):
    base_url = f"https://www.youtube.com/watch?v={id}"
    query_params_format = "&t={start}s"
    documents = []

    for chapter in chapters:
        text = chapter["text"].strip()
        start = chapter["time"]
        url = base_url + query_params_format.format(start=start)

        document = {"text": text, "metadata": {"source": url}}

        document["metadata"]["title"] = video_title
        document["metadata"]["chapter-title"] = chapter["title"]
        document["metadata"]["full-title"] = f"{video_title} - {chapter['title']}"

        documents.append(document)

    documents = etl.shared.enrich_metadata(documents)

    return documents


def merge(subtitles, idx):
    import srt

    new_content = combine_content(subtitles)

    # preserve start as timedelta
    new_start = seconds_float_to_timedelta(subtitles[0]["start"])
    # merge durations as timedelta
    new_duration = seconds_float_to_timedelta(sum(sub["duration"] for sub in subtitles))

    # combine
    new_end = new_start + new_duration

    return srt.Subtitle(index=idx, start=new_start, end=new_end, content=new_content)


def timestamp_from_timedelta(td):
    return int(td.total_seconds())


def combine_content(subtitles):
    contents = [subtitle["text"].strip() for subtitle in subtitles]
    return " ".join(contents) + "\n\n"


def get_charcount(subtitle):
    return len(subtitle["text"])


def seconds_float_to_timedelta(x_seconds):
    from datetime import timedelta

    return timedelta(seconds=x_seconds)
