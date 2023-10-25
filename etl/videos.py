from typing import Optional

import modal

import etl.shared

# type aliases, for documentation only
PlaylistId = str
VideoInfo = dict
VideoId = str
Chapter = dict
Document = dict  # really, a LangChain.Document
Subtitles = dict

# extend the shared image with YouTube-handling dependencies
image = etl.shared.image.pip_install("youtube-transcript-api==0.6.1", "srt==3.5.3")

# construct our app stub by adding secrets and mounts
stub = modal.Stub(
    name="etl-videos",
    image=image,
    secrets=[
        modal.Secret.from_name("mongodb-fsdl"),
    ],
    mounts=[
        # we make our local modules available to the container
        modal.Mount.from_local_python_packages("app.docstore", "app.utils")
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
def extract_subtitles(video_info: VideoInfo) -> list[Document]:
    video_id, video_title = video_info["id"], video_info["title"]
    subtitles = get_transcript.local(video_id)
    if subtitles is None:
        return []
    chapters = get_chapters.local(video_id)
    chapters = add_transcript.local(chapters, subtitles)

    documents = create_documents.local(chapters, video_id, video_title)

    return documents


@stub.function(concurrency_limit=10)
def get_transcript(video_id: VideoId) -> Optional[dict]:
    from youtube_transcript_api import YouTubeTranscriptApi

    try:
        return YouTubeTranscriptApi.get_transcript(video_id)
    except Exception:
        return None


@stub.function(
    retries=modal.Retries(max_retries=3, backoff_coefficient=2.0, initial_delay=5.0)
)
def get_chapters(video_id: VideoId) -> list[Chapter]:
    import requests

    base_url = "https://yt.lemnoslife.com"
    request_path = "/videos"

    params = {"id": video_id, "part": "chapters"}

    response = requests.get(base_url + request_path, params=params)
    response.raise_for_status()

    chapters = response.json()["items"][0]["chapters"]["chapters"]
    assert len(chapters) >= 0, "Response has no chapters"

    for chapter in chapters:
        del chapter["thumbnails"]

    if len(chapters) == 0:  # if there's no chapters, call it one big chapter
        chapters = [{"time": 0, "title": "Full Video"}]

    return chapters


@stub.function(
    retries=modal.Retries(max_retries=3, backoff_coefficient=2.0, initial_delay=5.0)
)
def get_playlist_videos(playlist_id: PlaylistId) -> list[VideoId]:
    """Get ids for all of the videos in a playlist"""
    import requests

    base_url = "https://yt.lemnoslife.com"
    request_path = "/playlistItems"

    params = {"playlistId": playlist_id, "part": "snippet"}

    response = requests.get(base_url + request_path, params=params)
    response.raise_for_status()

    raw_items = response.json()["items"]
    videos = [get_video_metadata(item["snippet"]) for item in raw_items]
    videos = [video for video in videos if video is not None]

    return videos


def get_video_metadata(snippet: dict) -> Optional[VideoInfo]:
    """Extract just the metadata we need from the YouTube API response."""
    try:
        assert snippet["resourceId"]["kind"] == "youtube#video"
        data = {"id": snippet["resourceId"]["videoId"], "title": snippet["title"]}
    except Exception:
        return None
    return data


@stub.function()
def add_transcript(chapters: list[Chapter], subtitles: Subtitles):
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


@stub.function(concurrency_limit=100)
def create_documents(
    chapters: list[Chapter], id: str, video_title: str
) -> list[Document]:
    """Convert the chapter subtitles of a video into a document collection."""
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
