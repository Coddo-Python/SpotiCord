"""This is a cog aimed at basic commands"""

import discord

from discord.ext import commands


class BasicCommands(commands.Cog):
    """This is a cog containing basic commands"""

    def __init__(self, client):
        self.client = client

    @commands.command(aliases=["ver"])
    async def version(self, ctx):
        """This is a command to show the bot's version"""
        embed = discord.Embed(title="Version", color=0x1DB954)
        embed.set_author(
            name=ctx.message.author.name, icon_url=ctx.message.author.avatar_url
        )
        embed.add_field(
            name="Stable", value="There is no Stable Version Yet!", inline=False
        )
        embed.add_field(
            name="Beta", value="Version 1.2 - The Gratissimum Update\n", inline=False
        )
        embed.set_footer(
            text="Made with ❤ by Coddo#3210",
            icon_url="https://cdn.discordapp.com/avatars"
            "/579646098704957460"
            "/93dabd1e5b999d95ae2a6f2d36a58249.png?size=256",
        )
        await ctx.send(embed=embed)

    @commands.command(aliases=["pong"])
    async def ping(self, ctx):
        """This is a command to show the bot's ping"""
        voice = discord.utils.get(self.client.voice_clients, guild=ctx.guild)
        embed = discord.Embed(title="Ping", color=0x1DB954)
        embed.set_author(
            name=ctx.message.author.name, icon_url=ctx.message.author.avatar_url
        )
        embed.add_field(
            name="API",
            value=f"The ping to the Discord API is **{round(self.client.latency * 1000)}ms**",
            inline=False,
        )
        if voice is None:
            embed.add_field(
                name="Voice",
                value="I am not connected to a voice channel on this server!",
                inline=False,
            )
        else:
            embed.add_field(
                name="Voice",
                value="The ping to the Discord Voice Chat Endpoint is "
                f"**{round(voice.latency * 1000)}ms**",
                inline=False,
            )
        embed.set_footer(
            text="Made with ❤ by Coddo#3210",
            icon_url="https://cdn.discordapp.com/avatars/579646098704957460"
            "/93dabd1e5b999d95ae2a6f2d36a58249.png?size=256",
        )
        await ctx.send(embed=embed)

    @commands.command(aliases=["whodidthis"])
    async def credits(self, ctx):
        """This is a command which shows the bot's credits"""
        embed = discord.Embed(title="Credits", color=0x1DB954)
        embed.set_author(
            name=ctx.message.author.name, icon_url=ctx.message.author.avatar_url
        )
        embed.add_field(
            name="Cool People!",
            value="Founder & Developer: Coddo#3210"
            "\nArtist: [ardt] Azu#6315\nTesters: I think we "
            "hired too many ;-;",
            inline=False,
        )
        embed.set_footer(
            text="Made with ❤ by Coddo#3210",
            icon_url="https://cdn.discordapp.com/avatars/579646098704957460"
            "/93dabd1e5b999d95ae2a6f2d36a58249.png?size=256",
        )
        await ctx.send(embed=embed)


def setup(client):
    """This is a setup function called by discord.py to setup the cog"""
    client.add_cog(BasicCommands(client))
