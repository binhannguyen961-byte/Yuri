import asyncio
import os
import threading
from flask import Flask
import discord
from discord.ext import commands
from google import genai
import yt_dlp

# ================= 1. CẤU HÌNH WEB SERVER (FLASK) =================
app = Flask(__name__)

@app.route('/')
def home():
    return "Yuri Bot is running fine!"

def run_flask():
    # Port mặc định là 8080 (hoặc lấy từ biến môi trường PORT của hosting)
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    """Khởi chạy Flask server trên một thread riêng biệt"""
    server_thread = threading.Thread(target=run_flask)
    server_thread.daemon = True
    server_thread.start()

# ================= 2. CẤU HÌNH CƠ BẢN BOT =================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "YOUR_DISCORD_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY")

# Khởi tạo AI Client
ai_client = genai.Client(api_key=GEMINI_API_KEY)

# Khởi tạo Discord Bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ================= 3. CẤU HÌNH TẢI & PHÁT NHẠC =================
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

queues = {}     # { guild_id: [ {'stream_url': ..., 'title': ...}, ... ] }
loop_status = {} # { guild_id: True/False }


def check_queue_and_play(ctx):
    """Hàm bổ trợ xử lý phát bài tiếp theo trong hàng đợi hoặc lặp lại"""
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
        ctx.send(f"🎶 Đang phát: **{song['title']}**"), bot.loop
    )


# ================= 4. LỆNH HƯỚNG DẪN (HELP) =================


@bot.command(name="help")
async def custom_help(ctx):
    """Hiển thị bảng danh sách các lệnh của Bot Yuri"""
    embed = discord.Embed(
        title="✨ Trợ lý & Phát nhạc Yuri - Bảng Lệnh ✨",
        description="Dưới đây là danh sách các lệnh bạn có thể sử dụng với Yuri:",
        color=discord.Color.purple(),
    )

    embed.add_field(
        name="🎵 **Âm Nhạc (SoundCloud)**",
        value=(
            "`!join` - Mời Yuri vào kênh thoại của bạn.\n"
            "`!play [link]` - Phát nhạc từ SoundCloud (hoặc thêm vào hàng đợi).\n"
            "`!pause` - Tạm dừng phát nhạc.\n"
            "`!resume` - Tiếp tục phát nhạc.\n"
            "`!skip` - Bỏ qua bài hát hiện tại để sang bài tiếp theo.\n"
            "`!loop` - Bật/tắt chế độ lặp lại bài hát hiện tại.\n"
            "`!queue` - Xem danh sách các bài hát đang chờ trong hàng đợi.\n"
            "`!stop` - Dừng phát nhạc, xóa hàng đợi và mời Yuri rời kênh thoại."
        ),
        inline=False,
    )

    embed.add_field(
        name="🤖 **Trí Tuệ Nhân Tạo (AI)**",
        value="`!ai [câu hỏi]` - Trò chuyện hoặc hỏi bất kỳ điều gì với Yuri.",
        inline=False,
    )

    embed.set_footer(text="Dùng tiền tố ! trước mỗi lệnh. Chúc bạn có trải nghiệm nghe nhạc vui vẻ!")
    await ctx.send(embed=embed)


# ================= 5. CÁC LỆNH ĐIỀU KHIỂN NHẠC =================


@bot.command(name="join")
async def join(ctx):
    if not ctx.author.voice:
        return await ctx.send("❌ Bạn phải vào một Voice Channel trước!")
    channel = ctx.author.voice.channel
    if ctx.voice_client:
        await ctx.voice_client.move_to(channel)
    else:
        await ctx.voice_client.connect()
    await ctx.send(f"🔊 Yuri đã kết nối tới **{channel.name}**")


@bot.command(name="play")
async def play(ctx, url: str):
    if not ctx.voice_client:
        await ctx.invoke(join)
        if not ctx.voice_client:
            return

    async with ctx.typing():
        loop = asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(
                None, lambda: ytdl.extract_info(url, download=False)
            )
        except Exception:
            return await ctx.send("❌ Không thể lấy dữ liệu từ link SoundCloud này!")

        if "entries" in data:
            data = data["entries"][0]

        song = {
            "stream_url": data["url"],
            "title": data.get("title", "Bài hát không tên"),
        }

        guild_id = ctx.guild.id
        if guild_id not in queues:
            queues[guild_id] = []

        if ctx.voice_client.is_playing() or ctx.voice_client.is_paused():
            queues[guild_id].append(song)
            await ctx.send(
                f"➕ Đã thêm vào hàng đợi: **{song['title']}** (Vị trí #{len(queues[guild_id])})"
            )
        else:
            ctx.voice_client.current_song = song
            source = discord.FFmpegPCMAudio(song["stream_url"], **FFMPEG_OPTIONS)
            ctx.voice_client.play(source, after=lambda e: check_queue_and_play(ctx))
            await ctx.send(f"🎶 Đang phát: **{song['title']}**")


@bot.command(name="queue")
async def show_queue(ctx):
    guild_id = ctx.guild.id
    if guild_id not in queues or len(queues[guild_id]) == 0:
        return await ctx.send("📜 Hàng đợi hiện đang trống!")

    msg = "**📜 Danh sách chờ phát nhạc:**\n"
    for idx, song in enumerate(queues[guild_id], start=1):
        msg += f"`{idx}.` {song['title']}\n"

    await ctx.send(msg)


@bot.command(name="skip")
async def skip(ctx):
    if ctx.voice_client and (
        ctx.voice_client.is_playing() or ctx.voice_client.is_paused()
    ):
        loop_status[ctx.guild.id] = False
        ctx.voice_client.stop()
        await ctx.send("⏭️ Đã bỏ qua bài hát hiện tại!")
    else:
        await ctx.send("❌ Hiện không có bài hát nào đang phát.")


@bot.command(name="pause")
async def pause(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸️ Đã tạm dừng nhạc.")


@bot.command(name="resume")
async def resume(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("▶️ Tiếp tục phát nhạc.")


@bot.command(name="loop")
async def loop(ctx):
    guild_id = ctx.guild.id
    current = loop_status.get(guild_id, False)
    loop_status[guild_id] = not current
    status_str = "bật 🔂" if not current else "tắt ➡️"
    await ctx.send(f"Chế độ lặp lại bài hát đã được **{status_str}**")


@bot.command(name="stop")
async def stop(ctx):
    guild_id = ctx.guild.id
    if guild_id in queues:
        queues[guild_id].clear()
    loop_status[guild_id] = False

    if ctx.voice_client:
        ctx.voice_client.stop()
        await ctx.voice_client.disconnect()
        await ctx.send("⏹️ Đã dừng nhạc, dọn sạch hàng đợi và rời khỏi phòng.")


# ================= 6. CÁC LỆNH TÍCH HỢP AI =================


@bot.command(name="ai")
async def ai_chat(ctx, *, prompt: str):
    async with ctx.typing():
        system_instruction = (
            "Bạn là Yuri, một trợ lý bot Discord thông minh, dịu dàng, thân thiện "
            "nhưng đôi lúc có chút dí dỏm. Hãy trả lời ngắn gọn, tự nhiên."
        )
        full_prompt = f"{system_instruction}\n\nNgười dùng hỏi: {prompt}"

        try:
            response = ai_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=full_prompt,
            )
            await ctx.send(response.text)
        except Exception:
            await ctx.send("💬 Xin lỗi, Yuri đang gặp sự cố khi xử lý câu hỏi này!")


# ================= 7. KHỞI CHẠY BOT VÀ FLASK =================


@bot.event
async def on_ready():
    print(f"✅ Bot Yuri đã sẵn sàng dưới tên: {bot.user.name}")


if __name__ == "__main__":
    # Khởi chạy Flask Server trên thread riêng
    keep_alive()
    
    # Khởi chạy Discord Bot
    bot.run(DISCORD_TOKEN)
