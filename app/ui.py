"""Builds a simple Gradio UI for interacting with the Q&A backend."""
import modal
from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from . import backend
from .utils import pretty_log


stub = backend.stub

VECTOR_DIR = backend.vecstore.VECTOR_DIR
vector_storage = modal.NetworkFileSystem.persisted("vector-vol")


web_app = FastAPI(docs_url=None)


@web_app.get("/", response_class=RedirectResponse, status_code=308)
async def root():
    return "/gradio"


@web_app.get("/docs", response_class=RedirectResponse, status_code=308)
async def redirect_docs():
    """Redirects to the Gradio subapi docs."""
    return "/gradio/docs"


@stub.function(
    network_file_systems={
        str(VECTOR_DIR): vector_storage,
    },
    keep_warm=1,
    concurrency_limit=1,  # turn off concurrency until state bug resolved
)
@modal.asgi_app(label="askfsdl-backend")
def fastapi_app():
    """A simple Gradio interface for debugging and playing around with the backend."""
    import gradio as gr
    from gradio.routes import mount_gradio_app
    import langsmith

    def chain_with_logging(*args, **kwargs):
        answer, metadata = backend.qanda.remote(*args, with_logging=True, **kwargs)
        return answer, metadata

    def on_flag(metadata, client, key):
        pretty_log(f"flagged with {key}")
        run_id = metadata.pop("run_id", None)
        if run_id is not None:
            pretty_log(f"logging feedback to LangSmith for {run_id}")
            client.create_feedback(run_id, key, score=True, source_info=metadata)

    interface = gr.Blocks(
        theme=gr.themes.Soft(
            font=[gr.themes.GoogleFont("Inconsolata"), "Arial"],
            radius_size="none",
            text_size=gr.themes.sizes.text_lg,
        ),
        title="Q&A",
    )

    with interface:
        client = langsmith.Client()

        def _on_flag(run_id, key="flagged"):
            return on_flag(run_id, client, key=key)

        flaggers = {
            "👍": lambda run_id: _on_flag(run_id, key="thumbs-up"),
            "👎": lambda run_id: _on_flag(run_id, key="thumbs-down"),
        }

        metadata = gr.State(value={})

        gr.HTML("<h1>🤖❓ Ask Questions About Building AI Systems</h1>")
        gr.HTML("<h2>🦜 Get sourced answers from an LLM</h2>")

        inputs = gr.Textbox(
            label="Question",
            value="What are the most important principles of MLOps?",
            show_label=True,
        )
        outputs = gr.TextArea(
            label="Answer", value="The answer will appear here.", show_label=True
        )

        with gr.Row():
            submit = gr.Button("Submit", variant="primary")
            submit.click(chain_with_logging, [inputs], [outputs, metadata])

        with gr.Row():
            for flagger_name, flagger_callback in flaggers.items():
                flagger = gr.Button(flagger_name)
                flagger.click(flagger_callback, [metadata])

        gr.Examples(
            [
                "Would you rather fight 100 LLaMA-sized GPT-4s or 1 GPT-4-sized LLaMA?",
                "Is it cheaper to run experiments on cheap GPUs or expensive GPUs?",
                "How do I recruit an ML team?",
                "What is the best way to learn about ML?",
                "What are the most important principles of MLOps?",
                "How can I use Ray with Kubernetes?",
            ],
            inputs,
        )

    return mount_gradio_app(
        app=web_app,
        blocks=interface,
        path="/gradio",
        app_kwargs={"docs_url": "/docs", "title": "ask-FSDL"},
    )
