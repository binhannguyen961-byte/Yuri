import os
import asyncio
import threading
from functools import partial
from flask import Flask
import discord
from discord.ext import commands
import yt_dlp
import requests
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# --- 1. Web Server ngầm giữ Render Online 24/7 ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Yuri Music Bot is Live!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- 2. Xử lý Link SoundCloud & Spotify ---
def resolve_url(url):
    if "on.soundcloud.com" in url:
        try:
            res = requests.get(url, allow_redirects=True, timeout=5)
            return res.url
        except Exception:
            return url
            
    if "open.spotify.com/track" in url:
        try:
            sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
                client_id=os.environ.get("SPOTIPY_CLIENT_ID", ""),
                client_secret=os.environ.get("SPOTIPY_CLIENT_SECRET", "")
            ))
            track_info = sp.track(url)
            return f"ytsearch:{track_info['name']} {track_info['artists'][0]['name']}"
        except Exception:
            return url

    return url

# --- 3. Cấu hình yt-dlp & FFmpeg ---
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
    'default_search': 'auto',
    'source_address': '0.0.0.0',
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

# Hàm lấy bài hát liên quan (Related Tracks) cho Autoplay
def get_related_track(url):
    try:
        # Bật trích xuất thông tin chi tiết để lấy danh sách gợi ý
        ydl_opts = YTDL_OPTIONS.copy()
        ydl_opts['noplaylist'] = False
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            # Lấy danh sách bài gợi ý nếu có
            if 'related_tracks' in info and len(info['related_tracks']) > 0:
                return info['related_tracks'][0].get('webpage_url') or info['related_tracks'][0].get('url')
            elif 'entries' in info and len(info['entries']) > 1:
                return info['entries'][1].get('webpage_url') or info['entries'][1].get('url')
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
        full_url = await loop.run_in_executor(None, resolve_url, url)
        to_run = partial(ytdl.extract_info, full_url, download=not stream)
        data = await loop.run_in_executor(None, to_run)

        if 'entries' in data:
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS), data=data)

# --- 4. Quản lý trạng thái Phát nhạc ---
music_queues = {}
loop_states = {}
autoplay_states = {}
current_songs = {}

def get_queue(ctx):
    if ctx.guild.id not in music_queues:
        music_queues[ctx.guild.id] = []
    return music_queues[ctx.guild.id]

# --- 5. Discord Bot của Yuri ---
intents = discord.Intents.default()
intents.message_content = True
yuri_bot = commands.Bot(command_prefix="!", intents=intents)

def play_next(ctx):
    guild_id = ctx.guild.id
    is_looping = loop_states.get(guild_id, False)
    is_autoplay = autoplay_states.get(guild_id, True) # Mặc định bật Autoplay
    queue = get_queue(ctx)

    # 1. Nếu bật Loop
    if is_looping and guild_id in current_songs:
        url, title = current_songs[guild_id]
        asyncio.run_coroutine_threadsafe(play_song(ctx, url, title), yuri_bot.loop)
        return

    # 2. Nếu có bài trong hàng chờ người dùng thêm vào
    if len(queue) > 0:
        url, title = queue.pop(0)
        asyncio.run_coroutine_threadsafe(play_song(ctx, url, title), yuri_bot.loop)
        return

    # 3. Tự động tìm bài liên quan (Autoplay SoundCloud/YouTube)
    if is_autoplay and guild_id in current_songs:
        last_url, _ = current_songs[guild_id]
        future = yuri_bot.loop.run_in_executor(None, get_related_track, last_url)
        
        async def handle_autoplay():
            related_url = await future
            if related_url:
                await ctx.send("*khẽ mỉm cười* Đang tự động phát bài hát tiếp theo liên quan cho cậu... 📻")
                await play_song(ctx, related_url, related_url)
            else:
                del current_songs[guild_id]

        asyncio.run_coroutine_threadsafe(handle_autoplay(), yuri_bot.loop)

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
    await yuri_bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="nhạc cùng cậu... 🎧"))

@yuri_bot.command(name='play', aliases=['p'])
async def play(ctx, *, url):
    if not ctx.author.voice:
        await ctx.send("*ngập ngừng* Cậu... cậu cần vào một kênh thoại trước đã...")
        return

    if ctx.voice_client is None:
        await ctx.author.voice.channel.connect()

    queue = get_queue(ctx)

    if ctx.voice_client.is_playing() or ctx.voice_client.is_paused():
        queue.append((url, url))
        await ctx.send(f"*cúi đầu* Tôi đã thêm bài hát này vào danh sách chờ cho cậu rồi nhé 🎵")
    else:
        await play_song(ctx, url, url)

@yuri_bot.command(name='autoplay', aliases=['ap'])
async def autoplay(ctx):
    guild_id = ctx.guild.id
    current_state = autoplay_states.get(guild_id, True)
    autoplay_states[guild_id] = not current_state

    if autoplay_states[guild_id]:
        await ctx.send("*gật đầu* Đã bật tự động tìm và phát bài liên quan khi hết nhạc 📻")
    else:
        await ctx.send("*nhìn cậu* Đã tắt tự động phát bài liên quan ⏹️")

@yuri_bot.command(name='loop', aliases=['l'])
async def loop(ctx):
    guild_id = ctx.guild.id
    loop_states[guild_id] = not loop_states.get(guild_id, False)
    status = "lặp lại bài hát hiện tại 🔁" if loop_states[guild_id] else "tắt lặp lại ➡️"
    await ctx.send(f"*đỏ mặt* Đã {status} cho cậu...")

@yuri_bot.command(name='skip', aliases=['s'])
async def skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        loop_states[ctx.guild.id] = False
        ctx.voice_client.stop()
        await ctx.send("*khẽ gật đầu* Tôi đã bỏ qua bài hát hiện tại...")

@yuri_bot.command(name='stop', aliases=['leave'])
async def stop(ctx):
    guild_id = ctx.guild.id
    if guild_id in music_queues:
        music_queues[guild_id].clear()
    loop_states[guild_id] = False

    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("*cúi đầu* Tôi xin phép rời khỏi kênh thoại nhé...")

if __name__ == "__main__":
    t_flask = threading.Thread(target=run_flask)
    t_flask.daemon = True
    t_flask.start()

    yuri_token = os.environ.get("DISCORD_TOKEN")
    if yuri_token:
        yuri_bot.run(yuri_token)
