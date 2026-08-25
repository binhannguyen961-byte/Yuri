import asyncio
import os
import threading
import discord
from discord.ext import commands
from flask import Flask
from google import genai
from google.genai import types
import yt_dlp

# ================= 1. WEB SERVER (FLASK) =================
app = Flask(__name__)

@app.route("/")
def home():
    return "Yuri (DDLC) is quietly reading..."

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    server_thread = threading.Thread(target=run_flask)
    server_thread.daemon = True
    server_thread.start()

# ================= 2. CẤU HÌNH BOT & GEMINI =================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "YOUR_DISCORD_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY")

ai_client = genai.Client(api_key=GEMINI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ================= 3. CẤU HÌNH NHẠC =================
YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "extractflat": False,
    "noplaylist": True,
    "quiet": True,
}

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)
queues = {}
loop_status = {}

def check_queue_and_play(ctx):
    guild_id = ctx.guild.id
    if loop_status.get(guild_id, False) and hasattr(ctx.voice_client, "current_song"):
        song = ctx.voice_client.current_song
    elif guild_id in queues and len(queues[guild_id]) > 0:
        song = queues[guild_id].pop(0)
        ctx.voice_client.current_song = song
    else:
        ctx.voice_client.current_song = None
        return

    source = discord.FFmpegPCMAudio(song["stream_url"], **FFMPEG_OPTIONS)
    ctx.voice_client.play(source, after=lambda e: check_queue_and_play(ctx))
    asyncio.run_coroutine_threadsafe(
        ctx.send(f"☕ Đang phát nhạc giúp bạn nè... **{song['title']}**"), bot.loop
    )

# ================= 4. LỆNH HELP (!Yhelps) =================
@bot.command(name="Yhelps")
async def custom_help(ctx):
    embed = discord.Embed(
        title="📖 Câu Lạc Bộ Văn Học - Sổ Tay Hướng Dẫn Của Yuri",
        description="X-Xin lỗi vì làm phiền... Dưới đây là các lệnh bạn có thể dùng:",
        color=discord.Color.from_rgb(108, 52, 131),
    )
    embed.add_field(
        name="🎶 **Âm Nhạc (SoundCloud)**",
        value=(
            "`!join` - Mời bot vào voice\n"
            "`!play [link]` - Phát nhạc\n"
            "`!pause` | `!resume` | `!skip` | `!loop` | `!queue` | `!stop`"
        ),
        inline=False,
    )
    embed.add_field(
        name="🔮 **Trò Chuyện AI**",
        value="`!ai [nội dung]` - Trò chuyện với Yuri",
        inline=False,
    )
    await ctx.send(embed=embed)

# ================= 5. LỆNH NHẠC =================
@bot.command(name="join")
async def join(ctx):
    if not ctx.author.voice:
        return await ctx.send("❌ Bạn phải vào phòng Voice Channel trước nhé...")
    channel = ctx.author.voice.channel
    if ctx.voice_client:
        await ctx.voice_client.move_to(channel)
    else:
        await ctx.voice_client.connect()
    await ctx.send(f"☕ Yuri đã vào **{channel.name}**...")

@bot.command(name="play")
async def play(ctx, url: str):
    if not ctx.voice_client:
        await ctx.invoke(join)
        if not ctx.voice_client:
            return

    async with ctx.typing():
        loop = asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
        except Exception as e:
            return await ctx.send(f"❌ Không thể tải nhạc: {e}")

        if "entries" in data:
            data = data["entries"][0]

        song = {"stream_url": data["url"], "title": data.get("title", "Bài hát không tên")}
        guild_id = ctx.guild.id
        if guild_id not in queues:
            queues[guild_id] = []

        if ctx.voice_client.is_playing() or ctx.voice_client.is_paused():
            queues[guild_id].append(song)
            await ctx.send(f"📝 Đã thêm **{song['title']}** vào danh sách chờ (#{len(queues[guild_id])}).")
        else:
            ctx.voice_client.current_song = song
            source = discord.FFmpegPCMAudio(song["stream_url"], **FFMPEG_OPTIONS)
            ctx.voice_client.play(source, after=lambda e: check_queue_and_play(ctx))
            await ctx.send(f"☕ Đang phát: **{song['title']}**")

@bot.command(name="queue")
async def show_queue(ctx):
    guild_id = ctx.guild.id
    if guild_id not in queues or len(queues[guild_id]) == 0:
        return await ctx.send("📜 Hàng đợi hiện đang trống.")
    msg = "**📜 Danh sách bài hát chờ:**\n"
    for idx, song in enumerate(queues[guild_id], start=1):
        msg += f"`{idx}.` {song['title']}\n"
    await ctx.send(msg)

@bot.command(name="skip")
async def skip(ctx):
    if ctx.voice_client and (ctx.voice_client.is_playing() or ctx.voice_client.is_paused()):
        loop_status[ctx.guild.id] = False
        ctx.voice_client.stop()
        await ctx.send("⏭️ Đã bỏ qua bài hát.")

@bot.command(name="pause")
async def pause(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸️ Đã tạm dừng.")

@bot.command(name="resume")
async def resume(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("▶️ Đã tiếp tục.")

@bot.command(name="loop")
async def loop(ctx):
    guild_id = ctx.guild.id
    current = loop_status.get(guild_id, False)
    loop_status[guild_id] = not current
    await ctx.send(f"Lặp lại: **{'Bật' if not current else 'Tắt'}**.")

@bot.command(name="stop")
async def stop(ctx):
    guild_id = ctx.guild.id
    if guild_id in queues:
        queues[guild_id].clear()
    loop_status[guild_id] = False
    if ctx.voice_client:
        ctx.voice_client.stop()
        await ctx.voice_client.disconnect()
        await ctx.send("⏹️ Đã dừng phát và rời phòng.")

# ================= 6. LỆNH AI AUTO-FALLBACK & DETAILED ERROR =================
@bot.command(name="ai")
async def ai_chat(ctx, *, prompt: str):
    async with ctx.typing():
        system_instruction = (
            "Bạn là Yuri trong Doki Doki Literature Club. "
            "Trả lời ngượng ngùng, rụt rè, cực kỳ lịch sự, từ ngữ chau chuốt. Xưng 'mình' hoặc 'Yuri', gọi người dùng là 'bạn'."
        )

        # Danh sách các tên model chuẩn thử nghiệm lần lượt
        candidate_models = ["gemini-2.5-flash", "gemini-2.0-flash-001", "gemini-2.0-flash"]
        response = None
        last_error = None

        loop = asyncio.get_event_loop()
        config = types.GenerateContentConfig(system_instruction=system_instruction)

        for model_name in candidate_models:
            try:
                response = await loop.run_in_executor(
                    None,
                    lambda m=model_name: ai_client.models.generate_content(
                        model=m,
                        contents=prompt,
                        config=config
                    )
                )
                if response and hasattr(response, "text") and response.text:
                    break
            except Exception as e:
                last_error = e
                print(f"Thử model {model_name} thất bại: {e}")
                continue

        if response and hasattr(response, "text") and response.text:
            reply_text = response.text
            if len(reply_text) > 1900:
                for chunk in [reply_text[i:i+1900] for i in range(0, len(reply_text), 1900)]:
                    await ctx.send(chunk)
            else:
                await ctx.send(reply_text)
        else:
            # Nếu thất bại toàn bộ, báo trực tiếp lỗi kỹ thuật lên Discord
            await ctx.send(f"⚠️ **Không thể gọi Gemini API.**\nChi tiết lỗi: `{last_error}`")

# ================= 7. CHẠY BOT =================
@bot.event
async def on_ready():
    print(f"✅ Bot online: {bot.user.name}")

if __name__ == "__main__":
    keep_alive()
    bot.run(DISCORD_TOKEN)
