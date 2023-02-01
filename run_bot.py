"""Run a Discord bot that does document Q&A using Modal."""
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



def main(targeted_channels, auth):
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
        if ctx.channel.id not in targeted_channels:
            return

        if ctx.author == bot.user:
            # ignore posts by self
            return
        else:
            respondent = ctx.author

        print(f"🤖: responding to question \"{question}\"")
        response = runner(question)  # execute
        await ctx.send(f"{respondent.mention} asked: {question}\n\nHere's my response, with sources so you can read more:\n\n{response}")  # respond

    bot.run(auth)


def make_argparser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dev", action="store_true", help="Run in development mode.")

    return parser


if __name__ == "__main__":
    parser = make_argparser()
    args = parser.parse_args()

    targeted_channels = [
        1066557596313604200, # main channel: `ask-fsdl`
    ]

    if args.dev:
        targeted_channels = [
        1066450466898186382, # dev channel: `ask-fsdl-dev`
        984528990368825395,  # `instructor-lounge`
        ]

    main(targeted_channels, auth=DISCORD_AUTH)
