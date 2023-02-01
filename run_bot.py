"""Run a Discord bot that does document Q&A using Modal and langchain."""
import argparse
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv
import requests

load_dotenv()

MODAL_USER_NAME = os.environ["MODAL_USER_NAME"]
BACKEND_URL = f"https://{MODAL_USER_NAME}--ask-fsdl-hook.modal.run"
DISCORD_AUTH = os.environ["DISCORD_AUTH"]


def runner(query):
    payload = {"query": query}
    response = requests.get(url=BACKEND_URL, params=payload)

    response.raise_for_status()

    return response.json()["answer"]


def main(auth):
    # Discord auth requires statement of "intents"
    #  we start with default behaviors
    intents = discord.Intents.default()
    #  and add reading messages
    intents.message_content = True

    # create the base bot
    bot = commands.Bot(intents=intents)

    @bot.event
    async def on_ready():
        print(f"🤖: {bot.user} is ready and online!")

    # add our command
    @bot.slash_command(name="ask", description="Answers questions about FSDL material.")
    async def answer(ctx, question: str):
        """Answers questions about FSDL material."""
        respondent = ctx.author

        print(f"🤖: responding to question \"{question}\"")
        await ctx.respond("Working on it!", ephemeral=True)
        response = runner(question)  # execute
        await ctx.send_followup(f"{respondent.mention} asked: {question}\n\nHere's my response, with sources so you can read more:\n\n{response}")  # respond

    bot.run(auth)


def make_argparser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dev", action="store_true", help="Run in development mode.")

    return parser


if __name__ == "__main__":
    main(auth=DISCORD_AUTH)
