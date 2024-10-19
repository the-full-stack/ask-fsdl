from enum import Enum
from fastapi import Request, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
import aiohttp
import json

from modal import Image, Mount, Secret, Stub, asgi_app
from utils import pretty_log

# Define the image for the Modal container
image = Image.debian_slim(python_version="3.10").pip_install("pynacl", "requests")
discord_secrets = [Secret.from_name("discord-secret-fsdl")]

# Define the Modal stub
stub = Stub(
    "askfsdl-discord",
    image=image,
    secrets=discord_secrets,
    mounts=[Mount.from_local_python_packages("utils")],
)

# Enum definitions for Discord interaction types
class DiscordInteractionType(Enum):
    PING = 1
    APPLICATION_COMMAND = 2

class DiscordResponseType(Enum):
    PONG = 1
    DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE = 5

class DiscordApplicationCommandOptionType(Enum):
    STRING = 3

@stub.function(keep_warm=1)
@asgi_app(label="askfsdl-discord-bot")
def app() -> FastAPI:
    app = FastAPI()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.post("/")
    async def handle_request(request: Request):
        """Verify incoming requests and handle valid commands."""
        body = await verify(request)
        data = json.loads(body.decode())

        if data.get("type") == DiscordInteractionType.PING.value:
            return {"type": DiscordResponseType.PONG.value}

        if data.get("type") == DiscordInteractionType.APPLICATION_COMMAND.value:
            question = data["data"]["options"][0]["value"]
            pretty_log(question)

            # Kick off the response in the background
            respond.spawn(
                question,
                data["application_id"],
                data["token"],
                data["member"]["user"]["id"],
            )

            return {
                "type": DiscordResponseType.DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE.value
            }

        raise HTTPException(status_code=400, detail="Bad request")

    return app

@stub.function()
async def respond(
    question: str,
    application_id: str,
    interaction_token: str,
    user_id: str,
):
    """Respond to a user's question by passing it to the language model."""
    import modal

    try:
        raw_response = await modal.Function.lookup(
            "askfsdl-backend", "qanda"
        ).remote.aio(question, request_id=interaction_token, with_logging=True)
        pretty_log(raw_response)

        response = construct_response(raw_response, user_id, question)
    except Exception as e:
        pretty_log("Error", e)
        response = construct_error_message(user_id)
    await send_response(response, application_id, interaction_token)

async def send_response(
    response: str,
    application_id: str,
    interaction_token: str,
):
    """Send a response to the user interaction."""
    interaction_url = (
        f"https://discord.com/api/v10/webhooks/{application_id}/{interaction_token}"
    )

    json_payload = {"content": response}

    async with aiohttp.ClientSession() as session:
        async with session.post(interaction_url, json=json_payload) as resp:
            if resp.status != 204:
                pretty_log(f"Failed to send response: {await resp.text()}")

async def verify(request: Request):
    """Verify that the request is from Discord."""
    from nacl.signing import VerifyKey
    from nacl.exceptions import BadSignatureError

    public_key = os.getenv("DISCORD_PUBLIC_KEY")
    verify_key = VerifyKey(bytes.fromhex(public_key))

    signature = request.headers.get("X-Signature-Ed25519")
    timestamp = request.headers.get("X-Signature-Timestamp")
    body = await request.body()

    message = timestamp.encode() + body
    try:
        verify_key.verify(message, bytes.fromhex(signature))
    except BadSignatureError:
        raise HTTPException(status_code=401, detail="Invalid request") from None

    return body

def construct_response(raw_response: str, user_id: str, question: str) -> str:
    """Wraps the backend's response in a message for Discord."""
    rating_emojis = {
        "👍": "if the response was helpful",
        "👎": "if the response was not helpful",
    }

    emoji_reaction_text = " or ".join(
        f"react with {emoji} {reason}" for emoji, reason
