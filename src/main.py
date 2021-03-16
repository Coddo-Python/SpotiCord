"""This is the main entry point of the bot"""

import os
import asyncio
import ctypes.util
import discord
import aiohttp
import dotenv

from discord.ext import commands

dotenv.load_dotenv()

# For now all intents are fine, but upon release, we must only enable intents which are needed
intents = discord.Intents().all()
client = commands.Bot(command_prefix="s!", intents=intents)

client.load_extension("Cogs.error_handler")
client.load_extension("Cogs.basic_commands")
client.load_extension("Cogs.music_player")

client.players = {}
client.serverplayers = {}


@client.event
async def on_ready():
    """This is an event which is called when the bot is ready"""
    client.session = aiohttp.ClientSession()
    guilds = str(len(client.guilds))
    await client.change_presence(
        status=discord.Status.online,
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{guilds} Servers",
        ),
    )
    # This is needed as without this, the voice feature won't work half the time,
    # no idea what causes this
    await asyncio.create_subprocess_shell("pip install pynacl --upgrade")
    opus_path = ctypes.util.find_library("opus")
    if opus_path:
        discord.opus.load_opus(opus_path)
    if not discord.opus.is_loaded() and os.name != "nt":
        raise Exception("Opus failed to load")
    print("--------")
    print(f"Logged in as: {client.user.name}")
    print(f"User ID: {client.user.id}")
    print("--------")
    print("--------")
    print("Bot Ready")
    print("--------")
    print("--------")
    print(f"Prefix set to {client.command_prefix}")
    print("--------")


@client.event
async def on_message(message: discord.Message):
    """An event which is called whenever a user sends a message"""
    if f"<@!{client.user.id}>" in message.content:
        channel = message.channel
        embed = discord.Embed(title="You @tted me!", color=0x36BD71)
        embed.add_field(
            name="Prefix", value=f"My Prefix is `{client.command_prefix}`", inline=False
        )
        embed.add_field(
            name="Help",
            value=f"My Help command is `{client.command_prefix}help`",
            inline=False,
        )
        await channel.send(embed=embed)
    await client.process_commands(message)


client.run(os.getenv("BOT-TOKEN"))

asyncio.get_event_loop().run_until_complete(client.session.close())
asyncio.get_event_loop().run_until_complete(client.database.conn.close())
