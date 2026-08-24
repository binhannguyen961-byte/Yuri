import os
import asyncio
import threading
import re
from functools import partial
from flask import Flask
import discord
from discord.ext import commands
import yt_dlp
import requests
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

app = Flask(__name__)

@app.route('/')
def home():
    return "Yuri Music Bot is Live!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# Spotify Client
SPOTIPY_CLIENT_ID = os.environ.get("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = os.environ.get("SPOTIPY_CLIENT_SECRET")
sp = None
if SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET:
    try:
        sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
            client_id=SPOTIPY_CLIENT_ID,
            client_secret=SPOTIPY_CLIENT_SECRET
        ))
    except Exception:
        pass

# Cấu hình yt-dlp tối ưu chống chặn bot & lỗi sign-in
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'audioformat': 'mp3',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

def clean_title(title):
    title = re.sub(r'[\(\[\{].*?[\)\]\}]', '', title)
    title = re.sub(r'http\S+|www\.\S+', '', title)
    return title.strip()

def get_related_track(song_title):
    try:
        search_query = f"ytsearch5:{clean_title(song_title)} music"
        with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
            info = ydl.extract_info(search_query, download=False)
            if 'entries' in info and len(info['entries']) > 1:
                selected = info['entries'][1]
                return selected.get('webpage_url') or selected.get('url')
    except Exception:
        pass
    return None

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('webpage_url') or data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True):
        loop = loop or asyncio.get_event_loop()
        query = url

        # Xử lý SoundCloud rút gọn
        if "on.soundcloud.com" in url:
            try:
                res = await loop.run_in_executor(None, lambda: requests.get(url, allow_redirects=True, timeout=5))
                query = res.url
            except Exception:
                query = url

        # Xử lý Spotify (Chuyển hẳn thành query tìm kiếm YouTube để tránh lỗi DRM)
        if "spotify.com/track/" in url and sp:
            try:
                track_info = await loop.run_in_executor(None, lambda: sp.track(url))
                query = f"ytsearch:{track_info['name']} {track_info['artists'][0]['name']}"
            except Exception:
                pass

        to_run = partial(ytdl.extract_info, query, download=not stream)
        data = await loop.run_in_executor(None, to_run)

        if 'entries' in data:
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS), data=data)

music_queues = {}
loop_states = {}
autoplay_states = {}
current_songs = {}

def get_queue(ctx):
    if ctx.guild.id not in music_queues:
        music_queues[ctx.guild.id] = []
    return music_queues[ctx.guild.id]

yuri_bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())

def play_next(ctx):
    guild_id = ctx.guild.id
    is_looping = loop_states.get(guild_id, False)
    is_autoplay = autoplay_states.get(guild_id, True)
    queue = get_queue(ctx)

    if is_looping and guild_id in current_songs:
        url, title = current_songs[guild_id]
        asyncio.run_coroutine_threadsafe(play_song(ctx, url, title), yuri_bot.loop)
        return

    if len(queue) > 0:
        url, title = queue.pop(0)
        asyncio.run_coroutine_threadsafe(play_song(ctx, url, title), yuri_bot.loop)
        return

    if is_autoplay and guild_id in current_songs:
        _, last_title = current_songs[guild_id]
        future = yuri_bot.loop.run_in_executor(None, get_related_track, last_title)
        
        async def handle_autoplay():
            related_url = await future
            if related_url:
                await ctx.send("*khẽ mỉm cười* Đang tự động phát bài hát tiếp theo cho cậu... 📻")
                await play_song(ctx, related_url, related_url)
            else:
                if guild_id in current_songs:
                    del current_songs[guild_id]

        asyncio.run_coroutine_threadsafe(handle_autoplay(), yuri_bot.loop)
    else:
        if guild_id in current_songs:
                    del current_songs[guild_id]

async def play_song(ctx, url, title):
    async with ctx.typing():
        try:
            player = await YTDLSource.from_url(url, loop=yuri_bot.loop, stream=True)
            current_songs[ctx.guild.id] = (player.url, player.title)
            ctx.voice_client.play(player, after=lambda e: play_next(ctx))
            await ctx.send(f"*mỉm cười e ấp* Đang phát nhạc cho cậu: **{player.title}** 🎶")
        except Exception as e:
            await ctx.send(f"*bối rối* Tôi gặp chút lỗi khi phát bài này: {str(e)}")
            play_next(ctx)

@yuri_bot.event
async def on_ready():
    print(f"-> Yuri Online: {yuri_bot.user}")

@yuri_bot.command(name='play', aliases=['p'])
async def play(ctx, *, url):
    if not ctx.author.voice:
        await ctx.send("*ngập ngừng* Cậu cần vào một kênh thoại trước đã...")
        return
    if ctx.voice_client is None:
        await ctx.author.voice.channel.connect()

    queue = get_queue(ctx)
    if ctx.voice_client.is_playing() or ctx.voice_client.is_paused():
        queue.append((url, url))
        await ctx.send("*cúi đầu* Đã thêm bài hát vào danh sách chờ 🎵")
    else:
        await play_song(ctx, url, url)

@yuri_bot.command(name='autoplay', aliases=['ap'])
async def autoplay(ctx):
    guild_id = ctx.guild.id
    autoplay_states[guild_id] = not autoplay_states.get(guild_id, True)
    status = "bật" if autoplay_states[guild_id] else "tắt"
    await ctx.send(f"*gật đầu* Đã {status} tự động phát bài liên quan 📻")

@yuri_bot.command(name='skip', aliases=['s'])
async def skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        loop_states[ctx.guild.id] = False
        ctx.voice_client.stop()
        await ctx.send("*khẽ gật đầu* Đã bỏ qua bài hiện tại...")

if __name__ == "__main__":
    t_flask = threading.Thread(target=run_flask)
    t_flask.daemon = True
    t_flask.start()

    yuri_token = os.environ.get("DISCORD_TOKEN")
    if yuri_token:
        yuri_bot.run(yuri_token)
