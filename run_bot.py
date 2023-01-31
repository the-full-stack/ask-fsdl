import os

import discord
from dotenv import load_dotenv

load_dotenv()

BACKEND_URL = "https://charlesfrye--ask-fsdl-web.modal.run"
DISCORD_AUTH = os.environ["DISCORD_AUTH"]

# Discord auth requirements: default behaviors
intents = discord.Intents.default()
# plus reading messages
intents.message_content = True

# connect to Discord
client = discord.Client(intents=intents)

# only read/write messages in certain channels
TARGETED_CHANNELS = [
    1066450466898186382, # dev channel: `ask-fsdl-dev`
    1066557596313604200, # main channel: `ask-fsdl`
    984528990368825395,  # `instructor-lounge`
]


def runner(query):
    import requests

    payload = {"query": query}
    response = requests.get(url=BACKEND_URL, params=payload)

    return response.json()["answer"]


@client.event
async def on_ready():
    print(f'We have logged in as {client.user}')


@client.event
async def on_message(message):
    if message.channel.id not in TARGETED_CHANNELS:
        return

    if message.author == client.user:
        # ignore posts by self
        return
    else:
        respondent = message.author


    if message.content.startswith('$ask-fsdl'):
        header, *content = message.content.split("$ask-fsdl")  # parse
        content =  "".join(content).strip()
        response = runner(content)  # execute
        await message.channel.send(f'{respondent.mention} {response}')  # respond


client.run(DISCORD_AUTH)
