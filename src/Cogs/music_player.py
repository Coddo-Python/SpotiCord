"""A cog for aimed for all music-based commands"""

# Sorry for messy imports, pylint was on some weird stuff

import asyncio
import os
import typing
import json

from datetime import datetime, timedelta
from ytmusicapi import YTMusic
from discord.ext import commands

import nest_asyncio
import pafy
import dotenv
import spotipy
import discord

from Utils import ytm

dotenv.load_dotenv()
nest_asyncio.apply()

ytmusic = YTMusic()
pafy.set_api_key(os.getenv("PAFY-TOKEN"))

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
auth_manager = spotipy.oauth2.SpotifyClientCredentials(CLIENT_ID, CLIENT_SECRET)
server_search_provider = spotipy.Spotify(auth_manager=auth_manager)
last_activity: typing.Dict[int, int] = {}


class MusicPlayer(commands.Cog):
    """The MusicPlayer cog which contains all music related commands and events"""

    def __init__(self, client):
        self.client = client

    @commands.command()
    async def listen_along(self, ctx: commands.Context, member: discord.Member):
        """The listen_along command which allows you to sync with another person's spotify stream"""
        if ctx.author.voice is None:
            return await ctx.send("You aren't in a VC!")
        voice = discord.utils.get(self.client.voice_clients, guild=ctx.guild)
        if voice is None:
            voice = await ctx.author.voice.channel.connect()
        if member.id not in self.client.players:
            spotify_activity = None
            for activity in member.activities:
                if isinstance(activity, discord.activity.Spotify):
                    spotify_activity = activity
            if not spotify_activity:
                # This can also be called if the spotify song name is too long
                # (Discord API Limitation)
                await ctx.send(
                    f"{member.display_name}'s Spotify was undetected. Make sure "
                    "their Spotify account is connected to Discord and that"
                    " they are playing a song!"
                )
            else:
                voice.stop()
                player = AudioPlayer(voice, member.id, spotify_activity)
                self.client.players[member.id] = player
                # Element 0 is the actual player itself, while element 1 is the position
                # of the server's audio handler in the list of audio handlers since
                # the bot only processes the audio once and sends out the same bytes
                # across all audio handlers
                self.client.serverplayers[ctx.guild.id] = [
                    self.client.players[member.id],
                    0,
                ]
                player.stop = False
                embed = discord.Embed(title="Loading...", color=0x1DB954)
                msg = await ctx.send(embed=embed)
                self.client.players[
                    member.id
                ].enhanced_precision_object = EnhancedPrecision(
                    self.client.players[member.id].activity
                )
                task = asyncio.create_task(
                    self.client.players[member.id].enhanced_precision()
                )
                await task
                await msg.edit(
                    embed=await MusicPlayer.get_nowplaying_embed(ctx, self.client)
                )
        else:
            # If other people are 'listening along' to this person already (in other servers)
            voice.stop()
            self.client.players[member.id].discord_audios.append(voice)
            # Refer to earlier in the function for an explanation of this
            self.client.serverplayers[ctx.guild.id] = [
                self.client.players[member.id],
                len(self.client.players[member.id].discord_audios) - 1,
            ]
            enhanced_precision = self.client.serverplayers[ctx.guild.id][0]
            enhanced_precision.stop = False
            track_data = enhanced_precision.enhanced_precision_object.data
            # Update timestamp of track so that another person can sync into it
            track_data["timestamp"] = (
                track_data["timestamp"]
                + enhanced_precision.enhanced_precision_calculation[0]
                + timedelta(seconds=enhanced_precision.timestamp)
            )
            # Execute what was in the enhanced_precision function, for more info refer there
            track = enhanced_precision.enhanced_precision_audio
            result = await enhanced_precision.simulate(
                track.url, track_data["duration"], track_data["timestamp"]
            )
            result = await enhanced_precision.simulate(
                track.url, track_data["duration"], track_data["timestamp"], result[0]
            )
            enhanced_precision.discord_audios[
                self.client.serverplayers[ctx.guild.id][1]
            ].play(
                result[1],
                after=lambda e: asyncio.new_event_loop().run_until_complete(
                    enhanced_precision.enhanced_after_play()
                ),
            )

    @commands.command()
    async def play(self, ctx, *, url):
        """A command to play songs from various sources"""
        voice = discord.utils.get(self.client.voice_clients, guild=ctx.guild)
        if voice is None:
            voice = await ctx.author.voice.channel.connect()
        if ctx.guild.id in self.client.serverplayers:
            if (
                self.client.serverplayers[ctx.guild.id][0].enhanced_precision_object
                is not None
            ):
                # Reset the enhanced precision, but keep it alive so that it can be
                # switched back to easily
                self.client.serverplayers[ctx.guild.id][0].stop = True
                await self.client.serverplayers[ctx.guild.id][0].stop_all()
                self.client.serverplayers[ctx.guild.id][0].discord_audios.pop(
                    self.client.serverplayers[ctx.guild.id][1]
                )
                self.client.serverplayers.pop(ctx.guild.id)
        self.client.serverplayers[ctx.guild.id] = [AudioPlayer(voice, None, None)]
        if "https://open.spotify.com/track/" in url:
            urltype = "Spotify"
            url = url.replace("https://open.spotify.com/track/", "").split("?", 1)[0]
        elif "https://open.spotify.com/playlist/" in url:
            urltype = "SpotifyPlay"
            url = url.replace("https://open.spotify.com/playlist/", "").split("?", 1)[0]
        elif "https://www.youtube.com/watch?v=" in url and len(url.split("&")[0]) == 43:
            urltype = "YoutubeLink"
        else:
            urltype = "YoutubeSearch"
        embed = discord.Embed(title="Loading...", color=0x1DB954)
        msg = await ctx.send(embed=embed)
        result = await self.client.serverplayers[ctx.guild.id][0].play(url, urltype)
        if result == "Song Not Found!":
            await msg.edit("Song Not Found!")
        else:
            await msg.edit(
                embed=await MusicPlayer.get_nowplaying_embed(ctx, self.client)
            )

    @commands.command(aliases=["joinme", "exist", "connect"])
    async def join(self, ctx: commands.Context):
        """A command to join the VC"""
        if ctx.author.voice is None:
            return await ctx.send("You aren't in a VC!")
        if discord.utils.get(self.client.voice_clients, guild=ctx.guild) is None:
            await ctx.author.voice.channel.connect()

    @commands.command(aliases=["bye", "exit", "byebye"])
    async def leave(self, ctx: commands.Context):
        """A command to leave the VC"""
        if self.client.serverplayers[ctx.guild.id][0].enhanced_precision_object:
            self.client.serverplayers[ctx.guild.id][0].discord_audios[
                self.client.serverplayers[ctx.guild.id][1]
            ].stop()
            self.client.serverplayers[ctx.guild.id][0].discord_audios.pop(
                self.client.serverplayers[ctx.guild.id][1]
            )
            self.client.serverplayers.pop(ctx.guild.id)
        else:
            self.client.serverplayers[ctx.guild.id][0].q = []
            await self.client.serverplayers[ctx.guild.id][0].stop_all()
        await ctx.voice_client.disconnect()

    # TODO: Finish me (Coddo's job)
    # @commands.command()
    # async def queue(self, ctx: commands.Context):
    #     if ctx.guild.id in self.client.serverplayers:
    #         current_trackdata = self.client.serverplayers[ctx.guild.id][0].metadata
    #         artists_str = ""
    #         for artist in current_trackdata["artists"]:
    #             if artists_str == "":
    #                 artists_str = f"{artist}"
    #             else:
    #                 artists_str += f", {artist}"
    #         embed = discord.Embed(title=f"Queue for {ctx.guild.name}", color=0x1DB954)
    #         embed.add_field(
    #             name="__Now Playing:__",
    #             value=f"[{artists_str} - {current_trackdata['name']}]"
    #             f"({current_trackdata['URL']}) "
    #             f"| {current_trackdata['duration']}",
    #             inline=False,
    #         )
    #         await ctx.send(embed=embed)

    @commands.command()
    async def skip(self, ctx: commands.Context):
        """A command to skip the current song"""
        if (
            self.client.serverplayers[ctx.guild.id][0].enhanced_precision_object
            is not None
        ):
            await self.client.serverplayers[ctx.guild.id].stop_all()
            await ctx.send("Song skipped!")

    @commands.command(
        aliases=["np", "waspopping", "whatspopping", "wutplaying", "whatplaying"]
    )
    async def nowplaying(self, ctx: commands.Context):
        """A command to show what is playing"""
        await ctx.send(embed=await MusicPlayer.get_nowplaying_embed(ctx, self.client))

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        """A cog to handle song changes in the listen_along feature"""
        global last_activity
        # This function will run for every server a member is in with the bot,
        # eg. the member is in 5 servers with the bot, this func will trigger 5 times.
        # So, this little bit of code here is meant to only trigger it once
        if after.id in last_activity:
            if last_activity[after.id] == len(after.mutual_guilds):
                last_activity[after.id] = 0
            elif last_activity[after.id] > 0:
                last_activity[after.id] += 1
                return
        else:
            last_activity[after.id] = 0
        for activity in after.activities:
            if isinstance(activity, discord.activity.Spotify):
                if after.id in self.client.players:
                    if (
                        activity
                        != self.client.players[
                            after.id
                        ].enhanced_precision_object.activity
                    ):
                        self.client.players[
                            after.id
                        ].enhanced_precision_object.activity = activity
                        await self.client.players[after.id].stop_all()
        last_activity[after.id] += 1

    @staticmethod
    async def get_nowplaying_embed(ctx, client):
        """A staticmethod to get the nowpalying embed"""
        trackdata = client.serverplayers[ctx.guild.id][0].metadata
        artists_str = ""
        timestamp = "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"
        chunks = int(trackdata["duration"] / 20)
        prev_chunk = 0
        for chunk in range(chunks, trackdata["duration"] + 1, chunks):
            if chunk >= client.serverplayers[ctx.guild.id][0].timestamp >= prev_chunk:
                use_chunk = chunk
                break
            prev_chunk += chunks
        timestamp = (
            timestamp[: int(use_chunk / chunks - 2)]
            + timestamp[int(use_chunk / chunks - 1)].replace("▬", "\\🟢")
            + timestamp[int(use_chunk / chunks - 1) :]
        )
        for artist in trackdata["artists"]:
            if artists_str == "":
                artists_str = f"{artist}"
            else:
                artists_str += f", {artist}"
        genre = (
            trackdata["genres"][0]
            if len(trackdata["genres"]) > 0
            else "Couldn't Determine"
        )
        if trackdata["is_explicit"]:
            embed = discord.Embed(
                title=f"<:Explicit:833616234692083721> {trackdata['name']}",
                color=0x1DB954,
                url=trackdata["URL"],
            )
        else:
            embed = discord.Embed(
                title=trackdata["name"], color=0x1DB954, url=trackdata["URL"]
            )
        embed.add_field(
            name="Info",
            value=f"Artists: {artists_str}\nGenre: {genre}\nAlbum Name: {trackdata['album_name']}"
            f"\nAlbum Release Date: {trackdata['album_release']}\n\n{timestamp} "
            f"{str(timedelta(seconds=client.serverplayers[ctx.guild.id][0].timestamp))}/"
            f"{str(timedelta(seconds=trackdata['duration']))}",
            inline=False,
        )
        embed.set_thumbnail(url=trackdata["album_art"])
        embed.set_footer(text="Made with ❤ by Coddo#3210", icon_url="")
        return embed


class AudioPlayer:
    """A class containing all backend code of the MusicPlayer cog"""

    def __init__(self, discord_audio, discord_id, activity):
        # Apparently pycharm says I should be declaring all class attributes here?
        self.enhanced_precision_object = None
        self.discord_audios = [discord_audio]
        self.id = discord_id
        self.activity = activity
        self.event_loop = asyncio.get_event_loop()
        self.tempdata = {"ended": 0}
        self.q = []
        self.stop = False
        self.enhanced_precision_RPC = None
        self.timestamp = 0
        self.enhanced_precision_calculation = None
        self.enhanced_precision_audio = None
        self.metadata = None

    async def play(  # pylint: disable=R1260
        self, url: str, url_type: str, from_queue: typing.Optional[bool] = False
    ) -> None:
        """
        ### Args
        - url: `str`, URL/URI of the song to be played
        - url_type: `str`, Type of URL/URI, eg. Youtube, Spotify, etc
        - from_queue: `Optional[bool]`, If the function was automatically called from the queue

        ### Returns
        - `None` If the song was found
        - `str` If the song wasn't found

        ### Errors raised
        - None

        ### Function / Notes
        - The after_play function is automatically executed once the current song is done
        playing/stopped
        """

        async def after_play():
            try:
                self.q.pop(0)
                await self.play(self.q[0][0], self.q[0][1], True)
            except IndexError:
                pass

        if not from_queue:
            if url_type == "Spotify":
                youtube_url = await EnhancedPrecision.get_track_youtube_url(url)
                metadata = await EnhancedPrecision.get_track_metadata(url)
                audio = await SpotiSearch.get_audio(youtube_url)
            elif url_type == "SpotifyPlay":
                tracks = await EnhancedPrecision.get_playlist_track_ids(url)
                self.q += [[track, "Spotify"] for track in tracks]
                metadata = await EnhancedPrecision.get_track_metadata(tracks[0])
                youtube_url = await EnhancedPrecision.get_track_youtube_url(tracks[0])
                audio = await SpotiSearch.get_audio(youtube_url)
            elif url_type == "YoutubeSearch":
                result = SpotiSearch(url)
                metadata = result[1]
                audio = result[0]
            else:
                result = await SpotiSearch.get_audio(url, True)
                metadata = result[1]
                audio = result[0]
            if audio == "Song Not Found!":
                return audio
        else:
            audio = url
            metadata = url_type
        if len(self.q) > 0 and not from_queue:
            self.q += [audio, metadata]
        else:
            ffmpeg_options = {
                # fixes the not playing last part of song bug
                "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
            }
            audio_source = discord.FFmpegPCMAudio(audio.url, **ffmpeg_options)
            self.metadata = metadata
            self.discord_audios[0].play(
                audio_source,
                after=lambda e: asyncio.new_event_loop().run_until_complete(
                    after_play()
                ),
            )
            if not self.enhanced_precision_RPC:
                self.timestamp = 0
                self.enhanced_precision_RPC = asyncio.create_task(
                    self.count(metadata["duration"])
                )

    async def enhanced_precision(self) -> None:
        """
        ### Args
        - None

        ### Returns
        - None

        ### Errors raised
        - None

        ### Function / Notes
        - There are 3 inner functions to allow for reduced encoding resources required
        if multiple people are listening along to the same person, pre_play will loop
        through the all the audio sources and accordingly play the track, and after_play
        will automatically find the next song once the current song is done playing.
        """

        async def play(discord_audio):
            discord_audio.play(
                result[1],
                after=lambda e: asyncio.new_event_loop().run_until_complete(
                    self.enhanced_after_play()
                ),
            )
            if not self.enhanced_precision_RPC:
                self.enhanced_precision_RPC = asyncio.create_task(
                    self.count(
                        track_data["duration"]
                        - int((track_data["timestamp"] + result[0]).total_seconds())
                    )
                )

        async def pre_play():
            if self.discord_audios == 0:
                return "No Audio Sources"
            coros = [play(x) for x in self.discord_audios]
            if self.enhanced_precision_RPC:
                self.enhanced_precision_RPC.cancel()
            self.enhanced_precision_RPC = None
            self.tempdata["ended"] = 0
            await asyncio.gather(*coros)

        self.metadata = None
        track_data = self.enhanced_precision_object.data
        track = await SpotiSearch.get_audio(track_data["youtube_url"])
        self.enhanced_precision_audio = track
        self.tempdata["ended"] = 0
        # Calculate encode time to adjust song timestamp accordingly
        result = await AudioPlayer.simulate(
            track.url, track_data["duration"], track_data["timestamp"]
        )
        result = await AudioPlayer.simulate(
            track.url, track_data["duration"], track_data["timestamp"], result[0]
        )
        self.enhanced_precision_calculation = result
        self.metadata = await EnhancedPrecision.get_track_metadata(
            track_data["track_id"]
        )
        error = await pre_play()
        if error == "No Audio Sources":
            return

    async def enhanced_after_play(self):
        """A function to be called once the current song playing
        has finished or stopped playing"""
        if not self.stop:
            if self.tempdata["ended"] == 0:
                await self.enhanced_precision_object.activity_to_data()
                self.tempdata["ended"] = 1
                await self.enhanced_precision()

    async def count(self, duration: int) -> None:
        """An RPC function to simply count in seconds how far
        the bot is into a song"""
        while self.timestamp < duration:
            await asyncio.sleep(1)
            self.timestamp += 1

    async def stop_all(self) -> None:
        """
        ### Args
        - None

        ### Returns
        - None

        ### Errors raised
        - None

        ### Function / Notes
        - This function is to stop all currently playing audio sources in `self`,
        this will play the next track in the queue if present
        """
        for x in self.discord_audios:
            x.stop()

    @staticmethod
    async def simulate(
        track_url: str,
        duration: float,
        timestamp: timedelta,
        addition: typing.Optional[timedelta] = timedelta(),
    ) -> typing.Tuple[timedelta, discord.FFmpegPCMAudio]:
        """
        ### Args
        - track_url: `str`, URL/URI of the track to be played
        - duration: `float`, Duration of the track to be played
        - timestamp: `timedelta`, Timestamp of track to skip to
        - addition: `Optional[timedelta]` Amount of time encoding takes, to move the
        timestamp accordingly

        ### Returns
        - `Tuple[timedelta, discord.FFmpegPCMAudio]` Tuple (to unpack) which contains
        the amount of time it took to encode the audio and the Discord audio source

        ### Errors raised
        - None

        ### Function / Notes
        - This function is just to initialize the enhanced_precision() because once its switched on,
        there is no turning back unless the class is deleted/overwrite(ed).
        """
        function_start_time = datetime.utcnow()
        timestamp += addition * 2
        seconds = timestamp.seconds % 60
        minutes = timestamp.seconds // 60
        if seconds < 10:
            seconds = f"0{str(seconds)}"
        options = {
            "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
            # fixes the not playing last part of song issue
            "options": f"-ss 00:{minutes}:{seconds} -to {duration}",
        }
        audio_source = discord.FFmpegPCMAudio(track_url, **options)
        time_taken = datetime.utcnow() - function_start_time
        return time_taken, audio_source


class EnhancedPrecision:
    """A class to contain all interactions with spotify"""

    def __init__(self, activity):
        self.activity = activity
        self.data = None
        self.event_loop = asyncio.get_event_loop()
        self.event_loop.run_until_complete(self.activity_to_data())

    @staticmethod
    async def get_track_youtube_url(track_id: str) -> str:
        """
        ### Args
        - track_id: `str`, URL/URI of track to be found

        ### Returns
        - `str` Track Youtube URL or "Song Not Found!"

        ### Errors raised
        - `requests.exceptions.ConnectionError`, Occurs when Python (urllib3) is unable to connect
        to the internet or the Spotify API

        ### Function / Notes
        - None
        """
        try:
            track = server_search_provider.track(track_id)
        except spotipy.exceptions.SpotifyException:
            return "Song Not Found!"
        artists = [artist["name"] for artist in track["album"]["artists"]]
        return ytm.get_youtube_link(
            track["name"],
            artists,
            track["album"]["name"],
            int(track["duration_ms"] / 1000),
        )

    @staticmethod
    async def get_album_track_ids(album_id: str) -> typing.Union[str, typing.List[str]]:
        """
        ### Args
        - album_id: `str`, URL/URI of album to be found

        ### Returns
        - `str` If the album wasn't found
        - `List[str]` List of tracks in the album if the album was found

        ### Errors raised
        - `requests.exceptions.ConnectionError`, Occurs when Python (urllib3) is unable to connect
        to the internet or the Spotify API

        ### Function / Notes
        - None
        """
        try:
            album = server_search_provider.album_tracks(album_id)
            while album["tracks"]["next"]:
                next_request = server_search_provider.next(album["tracks"])
                album["tracks"]["items"].extend(next_request["items"])
                album["tracks"]["next"] = next_request["next"]
        except spotipy.exceptions.SpotifyException:
            return "Song Not Found!"
        return [track["id"] for track in album["items"]]

    @staticmethod
    async def get_playlist_track_ids(
        playlist_id: str,
    ) -> typing.Union[str, typing.List[str]]:
        """
        ### Args
        - playlist_id: `str`, URL/URI of playlist to be found

        ### Returns
        - `str` If the playlist wasn't found
        - `List[str]` List of tracks in the playlist if the playlist was found

        ### Errors raised
        - `requests.exceptions.ConnectionError`, Occurs when Python (urllib3) is unable to connect
        to the internet or the Spotify API

        ### Function / Notes
        - None
        """
        try:
            playlist = server_search_provider.playlist_items(playlist_id)
            while playlist["next"]:
                next_request = server_search_provider.next(playlist)
                playlist["items"].extend(next_request["items"])
                playlist["next"] = next_request["next"]
        except spotipy.exceptions.SpotifyException:
            return "Song Not Found!"
        return [track["track"]["id"] for track in playlist["items"]]

    @staticmethod
    async def get_track_metadata_by_name(song_name: str) -> dict:
        """
        ### Args
        - song_name: `str`, name of the song to be found

        ### Returns
        - `dict`, metadata of the song found from song_name

        ### Errors raised
        - `requests.exceptions.ConnectionError`, Occurs when Python (urllib3) is unable to connect
        to the internet or the Spotify API

        ### Returned dict keys
        - URL: 'str', URL of the track
        - name: 'str', Name of the track
        - artists: 'List[str]', List of the track's artist(s)
        - genres: 'List[str]', List of possible genres of the track (can be empty)
        - is_explicit: 'bool', If the track is explicit or not
        - duration: 'int', Duration of the track in seconds
        - album_art: 'dict', Dict containing height (px), width (px) and url keys
        - album_name: 'str', Name of the track's album
        - album_artists: 'List[str]', List of contributing artists to the album
        - album_release: 'str', Date of album release (str) in the format '%Y-%m-%d'
        (Python datetime time format)
        """
        result = server_search_provider.search(q=song_name, limit=5, type="track")
        # This code fixes some song searches
        track = None
        for search in result["tracks"]["items"]:
            if song_name.lower() in search["name"].lower():
                track = search
                break
        return await EnhancedPrecision.__spotify_response_json_to_dict(
            track if track is not None else result["tracks"]["items"][0]
        )

    @staticmethod
    async def get_track_metadata(track_id: str) -> dict:
        """
        ### Args
        - track_id: `str`, URL/URI/ID of the track to be found

        ### Returns
        - `dict`, metadata of the track found from track_id

        ### Errors raised
        - `requests.exceptions.ConnectionError`, Occurs when Python (urllib3) is unable to connect
        to the internet or the Spotify API

        ### Returned dict keys
        - URL: 'str', URL of the track
        - name: 'str', Name of the track
        - artists: 'List[str]', List of the track's artist(s)
        - genres: 'List[str]', List of possible genres of the track (can be empty)
        - is_explicit: 'bool', If the track is explicit or not
        - duration: 'int', Duration of the track in seconds
        - album_art: 'dict', Dict containing height (px), width (px) and url keys
        - album_name: 'str', Name of the track's album
        - album_artists: 'List[str]', List of contributing artists to the album
        - album_release: 'str', Date of album release (str) in the format '%Y-%m-%d'
        (Python datetime time format)
        """
        return await EnhancedPrecision.__spotify_response_json_to_dict(
            server_search_provider.track(track_id)
        )

    async def activity_to_data(
        self, activity: typing.Optional[typing.Any] = None
    ) -> dict:
        """
        ### Args
        - activity: `Optional[Any]`, The activity to use instead of self.activity

        ### Returns
        - `dict` Metadata of track

        ### Errors raised
        - `requests.exceptions.ConnectionError`, Occurs when Python (urllib3) is unable to connect
        to the internet or the Spotify API

        ### Function / Notes
        - URL: 'str', URL of the track
        - name: 'str', Name of the track
        - artists: 'List[str]', List of the track's artist(s)
        - genres: 'List[str]', List of possible genres of the track (can be empty)
        - is_explicit: 'bool', If the track is explicit or not
        - duration: 'int', Duration of the track in seconds
        - album_art: 'dict', Dict containing height (px), width (px) and url keys
        - album_name: 'str', Name of the track's album
        - album_artists: 'List[str]', List of contributing artists to the album
        - album_release: 'str', Date of album release (str) in the format '%Y-%m-%d'
        (Python datetime time format)
        """
        activity = activity or self.activity
        more_track_data = await EnhancedPrecision.get_track_metadata(activity.track_id)
        self.data = {
            "name": activity.title,
            "URL": f"https://open.spotify.com/track/{activity.track_id}",
            "timestamp": datetime.utcnow() - activity.start,
            "duration": int(activity.duration.total_seconds()),
            "is_explicit": more_track_data["is_explicit"],
            "track_id": activity.track_id,
            "album_art": activity.album_cover_url,
            "album_name": activity.album,
            "artists": activity.artists,
            "youtube_url": ytm.get_youtube_link(
                activity.title,
                activity.artists,
                activity.album,
                activity.duration.total_seconds(),
            ),
        }
        with open("song_override.json") as f:
            data = json.load(f)
            for key, value in data.items():
                if key == self.data["track_id"]:
                    self.data["youtube_url"] = value
        return self.data

    @staticmethod
    async def youtube_to_metadata(youtube_data: dict) -> dict:
        """
        ### Args
        - youtube_data: `dict`, Youtube metadata from ytm.py

        ### Returns
        - `dict`, Metadata of the video

        ### Errors raised
        - `requests.exceptions.ConnectionError`, Occurs when Python (urllib3) is unable to connect
        to the internet or the Spotify API

        ### Returned dict keys
        - URL: 'str', URL of the track
        - name: 'str', Name of the track
        - artists: 'List[str]', List of the track's artist(s)
        - genres: 'List[str]', List of possible genres of the track (can be empty)
        - is_explicit: 'bool', If the track is explicit or not
        - duration: 'int', Duration of the track in seconds
        - album_art: 'dict', url of album_art
        - album_name: 'str', Name of the track's album
        - album_artists: 'List[str]', List of contributing artists to the album
        - album_release: 'str', Date of album release (str) in the format '%Y-%m-%d'
        (Python datetime time format)
        """
        prediction = await EnhancedPrecision.get_track_metadata_by_name(
            youtube_data["title"]
        )
        ytmusic_album = ytmusic.get_album(youtube_data["album"]["id"])
        releaseDate = ytmusic_album["releaseDate"]
        try:
            duration_strp = datetime.strptime(youtube_data["duration"], "%H:%M:%S")
        except ValueError:
            duration_strp = datetime.strptime(youtube_data["duration"], "%M:%S")
        duration = timedelta(
            hours=duration_strp.hour,
            minutes=duration_strp.minute,
            seconds=duration_strp.second,
        )
        return {
            "name": youtube_data["title"],
            "URL": f"https://www.youtube.com/watch?v={youtube_data['videoId']}",
            "artists": [artist["name"] for artist in youtube_data["artists"]],
            "genres": prediction["genres"],
            "is_explicit": youtube_data["isExplicit"],
            "duration": int(duration.total_seconds()),
            "album_art": youtube_data["thumbnails"][-1]["url"],
            "album_name": youtube_data["album"]["name"],
            "album_artists": [artist["name"] for artist in ytmusic_album["artist"]],
            "album_release": f"{releaseDate['year']}-"
            f"{releaseDate['month'] if len(str(releaseDate['month'])) == 2 else releaseDate['month']:02}"
            f"-{releaseDate['day']}",
        }

    @staticmethod
    async def __spotify_response_json_to_dict(
        track: dict, album: typing.Optional[dict] = None
    ) -> dict:
        """
        ### Args
        - track: `dict`, Track data to be used to return metadata
        - album: `Optional[dict]`, Album data to replace track album data (needed for get_album)

        ### Returns
        - `dict`, Metadata of track

        ### Errors raised
        - `requests.exceptions.ConnectionError`, Occurs when Python (urllib3) is unable to connect
        to the internet or the Spotify API

        ### Returned dict keys
        - URL: 'str', URL of the track
        - name: 'str', Name of the track
        - artists: 'List[str]', List of the track's artist(s)
        - genres: 'List[str]', List of possible genres of the track (can be empty)
        - is_explicit: 'bool', If the track is explicit or not
        - duration: 'int', Duration of the track in seconds
        - album_art: 'dict', url of album_art
        - album_name: 'str', Name of the track's album
        - album_artists: 'List[str]', List of contributing artists to the album
        - album_release: 'str', Date of album release (str) in the format '%Y-%m-%d'
        (Python datetime time format)
        """
        if album is None:
            album = server_search_provider.album(
                track["album"]["external_urls"]["spotify"]
            )
        artist = server_search_provider.artist(
            track["artists"][0]["external_urls"]["spotify"]
        )
        return {
            "URL": track["external_urls"]["spotify"],
            "name": track["name"],
            "artists": [artist["name"] for artist in track["artists"]],
            "genres": (album["genres"] + artist["genres"]),
            "is_explicit": track["explicit"],
            "duration": int(track["duration_ms"] / 1000),
            "album_art": album["images"][0]["url"],
            "album_name": album["name"],
            "album_artists": [artist["name"] for artist in album["artists"]],
            "album_release": album["release_date"],
        }


class SpotiSearch:
    """A class containing tools to download and search for songs"""

    def __new__(cls, search):
        data = ytmusic.search(search, "songs", 1)[0]
        return asyncio.get_event_loop().run_until_complete(
            SpotiSearch.get_audio(f'https://www.youtube.com/watch?v={data["videoId"]}')
        ), asyncio.get_event_loop().run_until_complete(
            EnhancedPrecision.youtube_to_metadata(data)
        )

    @staticmethod
    async def get_audio(
        url: str, return_metadata: bool = False
    ) -> typing.Union[str, typing.Any]:
        """
        ### Args
        - url: `str`, URL/URI of the Youtube video to download

        ### Returns
        - `str` If the Youtube video wasn't found
        - `Any` Pafy stream object if the Youtube video was found

        ### Errors raised
        - None

        ### Function / Notes
        - Pafy is used as it is the fastest audio/video downloader
        at an average of 0.5 seconds per 3 minutes on 150 mbps internet
        while youtube dl takes 1 second and pytube 9 seconds
        """
        try:
            song = pafy.new(url)
        except OSError or ValueError:
            return "Song Not Found!"
        audio = song.getbestaudio()
        if return_metadata:
            return audio, song
        return audio


def setup(client):
    """This is a setup function called by discord.py to setup the cog"""
    client.add_cog(MusicPlayer(client))
