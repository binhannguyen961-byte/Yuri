import os
import asyncio
import threading
from flask import Flask
import discord
from discord.ext import commands
import yt_dlp

# --- 1. Web Server giữ Render Online 24/7 ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Yuri Music Bot is Live!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- 2. YURI BOT (PHÁT NHẠC - ĐÃ SỬA LỖI SOUNDCLOUD) ---
yt_dlp.utils.bug_reports_message = lambda: ''
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
    'force_generic_extractor': False,
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True):
        loop = loop or asyncio.get_event_loop()
        
        # Định nghĩa hàm riêng để tránh lỗi keyword argument 'before'
        def fetch_info():
            return ytdl.extract_info(url, download=not stream)

        data = await loop.run_in_executor(None, fetch_info)
        if 'entries' in data:
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS), data=data)

intents = discord.Intents.default()
intents.message_content = True
yuri_bot = commands.Bot(command_prefix="!", intents=intents)

@yuri_bot.event
async def on_ready():
    print(f"-> Yuri Online: {yuri_bot.user}")
    await yuri_bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="nhạc cùng cậu... 🎧"))

@yuri_bot.command(name='play', aliases=['p'])
async def play(ctx, *, url):
    if not ctx.author.voice:
        await ctx.send("*ngập ngừng* Cậu... cậu cần vào một kênh thoại trước đã...")
        return

    channel = ctx.author.voice.channel
    if ctx.voice_client is None:
        await channel.connect()

    async with ctx.typing():
        try:
            player = await YTDLSource.from_url(url, loop=yuri_bot.loop, stream=True)
            ctx.voice_client.play(player, after=lambda e: print(f'Lỗi: {e}') if e else None)
            await ctx.send(f"*mỉm cười e ấp* Đang phát nhạc cho cậu: **{player.title}** 🎶")
        except Exception as e:
            await ctx.send(f"*bối rối* Tôi gặp chút lỗi khi phát bài này: {str(e)}")

@yuri_bot.command(name='stop', aliases=['leave'])
async def stop(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("*cúi đầu* Tôi xin phép rời khỏi kênh thoại nhé...")

if __name__ == "__main__":
    # 1. Chạy Web Server trên luồng phụ
    t_flask = threading.Thread(target=run_flask)
    t_flask.daemon = True
    t_flask.start()

    # 2. Chạy Yuri Bot trên luồng chính
    yuri_token = os.environ.get("DISCORD_TOKEN")
    if yuri_token:
        yuri_bot.run(yuri_token)
    else:
        print("Lỗi: Không tìm thấy DISCORD_TOKEN trong biến môi trường!")
