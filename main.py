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
    return "Yuri Music Bot is Online!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- 2. Cấu hình Yt-dlp & FFmpeg ---
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
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        if 'entries' in data:
            data = data['entries'][0]
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS), data=data)

# --- 3. Cấu hình Discord Bot cho Yuri ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"-> Yuri đã kết nối Discord thành công: {bot.user}")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="nhạc cùng cậu... 🎧"))

# --- Lệnh Phát Nhạc ---
@bot.command(name='play', aliases=['p'], help='Phát nhạc từ link hoặc từ khóa tìm kiếm')
async def play(ctx, *, url):
    if not ctx.author.voice:
        await ctx.send("*ngập ngừng* Cậu... cậu cần vào một kênh thoại (Voice Channel) trước đã...")
        return

    channel = ctx.author.voice.channel
    if ctx.voice_client is None:
        await channel.connect()

    async with ctx.typing():
        try:
            player = await YTDLSource.from_url(url, loop=bot.loop, stream=True)
            ctx.voice_client.play(player, after=lambda e: print(f'Lỗi nhạc: {e}') if e else None)
            await ctx.send(f"*mỉm cười e ấp* Đang phát nhạc cho cậu đây: **{player.title}** 🎶")
        except Exception as e:
            await ctx.send(f"*bối rối* Tôi gặp chút lỗi khi phát bài này rồi: {str(e)}")

# --- Lệnh Dừng/Thoát Kênh ---
@bot.command(name='stop', aliases=['leave'], help='Dừng phát nhạc và rời phòng')
async def stop(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("*cúi đầu* Tôi xin phép rời khỏi kênh thoại nhé...")
    else:
        await ctx.send("*nhìn cậu* Tôi đang không ở trong kênh thoại nào cả...")

# --- Lệnh Tạm Dừng / Tiếp Tục ---
@bot.command(name='pause', help='Tạm dừng nhạc')
async def pause(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("*thì thầm* Đã tạm dừng nhạc rồi...")

@bot.command(name='resume', help='Tiếp tục phát nhạc')
async def resume(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("*mỉm cười* Tiếp tục phát nhạc nhé...")

# --- 4. Khởi chạy ---
if __name__ == "__main__":
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()

    discord_token = os.environ.get("DISCORD_TOKEN")
    if discord_token:
        bot.run(discord_token)
    else:
        print("LỖI: Chưa nhập DISCORD_TOKEN trong Environment!")
