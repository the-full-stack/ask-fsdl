"""Run a Discord bot that does document Q&A using Modal."""
import argparse
import os

import discord
from dotenv import load_dotenv
import requests

load_dotenv()

MODAL_USER_NAME = os.environ["MODAL_USER_NAME"]
BACKEND_URL = f"https://{MODAL_USER_NAME}--ask-fsdl-hook.modal.run"
DISCORD_AUTH = os.environ["DISCORD_AUTH"]
BASE_TRIGGER_PHRASE = "$ask-fsdl"


def runner(query):
    payload = {"query": query}
    response = requests.get(url=BACKEND_URL, params=payload)

    response.raise_for_status()

    return response.json()["answer"]


def main(targeted_channels, trigger_phrase, auth):
    # Discord auth requires statement of "intents"
    #  we start with default behaviors
    intents = discord.Intents.default()
    #  and add reading messages
    intents.message_content = True
    # then connect to Discord
    client = discord.Client(intents=intents)


    # define the bot's behavior
    @client.event
    async def on_ready():
        print(f'We have logged in as {client.user}')


    @client.event
    async def on_message(message):
        if message.channel.id not in targeted_channels:
            return

        if message.author == client.user:
            # ignore posts by self
            return
        else:
            respondent = message.author

        if message.content.startswith(trigger_phrase):
            header, *content = message.content.split(trigger_phrase)  # parse
            content =  "".join(content).strip()
            print(f"🤖: responding to message \"{content}\"")
            response = runner(content)  # execute
            await message.channel.send(f'{respondent.mention} {response}')  # respond

    client.run(auth)


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
    trigger_phrase = BASE_TRIGGER_PHRASE

    if args.dev:
        targeted_channels = [
        1066450466898186382, # dev channel: `ask-fsdl-dev`
        984528990368825395,  # `instructor-lounge`
        ]
        trigger_phrase = "$dev-" + BASE_TRIGGER_PHRASE.strip("$")

    main(targeted_channels, trigger_phrase, auth=DISCORD_AUTH)
