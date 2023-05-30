"""Run a Discord bot frontend for the document Q&A backend."""
import argparse
import asyncio
import logging
import os

import aiohttp
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

MAINTAINER_ID = os.environ.get("DISCORD_MAINTAINER_ID")
MODAL_USER_NAME = os.environ["MODAL_USER_NAME"]
BACKEND_URL = f"https://{MODAL_USER_NAME}--ask-fsdl-hook.modal.run"

guild_ids = {
    "dev": 1070516629328363591,
    "prod": 984525101678612540,
}

START, END = "\033[1;36m", "\033[0m"


async def runner(query, request_id=None):
    payload = {"query": query}
    if request_id:
        payload["request_id"] = request_id
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url=BACKEND_URL, params=payload) as response:
                assert response.status == 200
                json_content = await response.json()
                return json_content["answer"]
        except Exception as e:
            pretty_log(f"Error: {e}")
            return "_error"


def main(auth, guilds, dev=False):
    # Discord auth requires statement of "intents"
    #  we start with default behaviors
    intents = discord.Intents.default()
    #  and add reading messages
    intents.message_content = True

    bot = commands.Bot(intents=intents, guilds=guilds)

    rating_emojis = {
        "👍": "if the response was helpful",
        "👎": "if the response was not helpful",
    }

    emoji_reaction_text = " or ".join(
        f"react with {emoji} {reason}" for emoji, reason in rating_emojis.items()
    )
    emoji_reaction_text = emoji_reaction_text.capitalize() + "."

    @bot.event
    async def on_ready():
        pretty_log(f"{bot.user} is ready and online!")

    response_fmt = """{mention} asked: {question}

    Here's my best guess at an answer, with sources so you can follow up:

    {answer}

    Emoji react to let us know how we're doing!

    """

    response_fmt += emoji_reaction_text

    # add our command
    @bot.slash_command(name="ask")
    @discord.option(
        "question", str, description="A question about anything covered by FSDL."
    )
    async def answer(ctx, question: str):
        """Answers questions about FSDL material."""

        respondent = ctx.author

        pretty_log(f'responding to question "{question}"')
        await ctx.defer(ephemeral=False, invisible=False)
        original_message = await ctx.interaction.original_response()
        message_id = original_message.id
        answer = await runner(question, request_id=message_id)
        answer.strip()
        if answer == "_error":
            error_response = f"Sorry {respondent.mention}, something went wrong."
            error_response = (
                error_response + f" I've let <@{MAINTAINER_ID}> know."
                if MAINTAINER_ID and respondent.id != int(MAINTAINER_ID)
                else error_response
            )
            error_response += " Please try again later."
            await ctx.respond(error_response)
        else:
            await ctx.respond(
                response_fmt.format(
                    mention=respondent.mention, question=question, answer=answer
                )
            )  # respond
            for emoji in rating_emojis:
                await original_message.add_reaction(emoji)
                await asyncio.sleep(0.25)

    if dev:

        @bot.slash_command()
        async def health(ctx):
            "Supports a Discord bot version of a liveness probe."
            pretty_log("inside healthcheck")
            await ctx.respond("200 more like 💯 mirite")

    bot.run(auth)


def make_argparser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dev", action="store_true", help="Run in development mode.")

    return parser


def pretty_log(str):
    print(f"{START}🤖: {str}{END}")


if __name__ == "__main__":
    args = make_argparser().parse_args()
    if args.dev:
        guilds = [guild_ids["dev"]]
        auth = os.environ["DISCORD_AUTH_DEV"]
    else:
        guilds = [guild_ids["prod"]]
        auth = os.environ["DISCORD_AUTH"]
    if args.dev:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    main(auth=auth, guilds=guilds, dev=args.dev)
