import modal

import etl.shared

# extend the shared image with YouTube-handling dependencies
image = etl.shared.image.pip_install("youtube-transcript-api", "srt")

stub = modal.Stub(
    name="etl-videos",
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
def main(json_path="data/videos.json"):
    """Calls the ETL pipeline using a JSON file with YouTube video metadata.

    modal run etl/videos.py --json-path /path/to/json
    """
    import json

    with open(json_path) as f:
        video_infos = json.load(f)

    video_ids = [video["id"] for video in video_infos]

    documents = (
        etl.shared.unchunk(  # each video creates multiple documents, so we flatten
            extract_subtitles.map(video_ids, return_exceptions=True)
        )
    )

    with etl.shared.stub.run():
        chunked_documents = etl.shared.chunk_into(documents, 10)
        list(etl.shared.add_to_document_db.map(chunked_documents))


@stub.function()
def extract_subtitles(video_id):
    subtitles = get_transcript(video_id)
    merged_subtitles = merge_subtitles(subtitles)
    return create_documents(merged_subtitles, video_id)


def get_transcript(video_id):
    from youtube_transcript_api import YouTubeTranscriptApi

    return YouTubeTranscriptApi.get_transcript(video_id)


def merge_subtitles(subtitles):
    TRIGGER_LENGTH = 750  # 30-60 seconds

    merged_subtitles = []
    current_chunk, current_length, chunk_idx = [], 0, 1

    for subtitle in subtitles:
        current_chunk.append(subtitle)
        added_length = get_charcount(subtitle)
        new_length = current_length + added_length

        if new_length >= TRIGGER_LENGTH:
            merged_subtitle = merge(current_chunk, chunk_idx)
            merged_subtitles.append(merged_subtitle)
            current_chunk, current_length = [], 0
            chunk_idx += 1
        else:
            current_length = new_length

    if current_chunk:
        merged_subtitle = merge(current_chunk, chunk_idx)
        merged_subtitles.append(merged_subtitle)

    return merged_subtitles


def create_documents(subtitles, id):
    base_url = f"https://www.youtube.com/watch?v={id}"
    query_params_format = "&t={start}s"
    documents = []

    for subtitle in subtitles:
        raw_text = subtitle.content
        text = raw_text.strip()
        start = timestamp_from_timedelta(subtitle.start)
        url = base_url + query_params_format.format(start=start)

        document = {"text": text, "metadata": {"source": url}}

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
