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
    return "Yuri (DDLC) is quietly reading..."

def run_flask():
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

# Khởi tạo Discord Bot với prefix '!' và loại bỏ help mặc định
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
        ctx.send(f"☕ Đang phát nhạc giúp bạn nè... **{song['title']}**"), bot.loop
    )


# ================= 4. LỆNH HƯỚNG DẪN (!Yhelps) =================


@bot.command(name="Yhelps")
async def custom_help(ctx):
    """Hiển thị bảng danh sách các lệnh của Bot Yuri"""
    embed = discord.Embed(
        title="📖 Câu Lạc Bộ Văn Học - Sổ Tay Hướng Dẫn Của Yuri",
        description=(
            "X-Xin lỗi vì làm phiền... Mình là Yuri. Nếu bạn muốn mình phát chút nhạc "
            "để đọc sách hoặc trò chuyện cùng mình, dưới đây là các lệnh bạn có thể dùng..."
        ),
        color=discord.Color.from_rgb(108, 52, 131), # Tông màu tím đặc trưng của Yuri
    )

    embed.add_field(
        name="🎶 **Giai Điệu & Âm Nhạc (SoundCloud)**",
        value=(
            "`!join` - Mời mình vào phòng thoại cùng nghe nhạc với bạn.\n"
            "`!play [link]` - Phát bài hát từ SoundCloud (hoặc xếp vào danh sách đọc).\n"
            "`!pause` - Tạm dừng giai điệu một chút.\n"
            "`!resume` - Tiếp tục giai điệu đang dở dang.\n"
            "`!skip` - Bỏ qua bài hát này.\n"
            "`!loop` - Phát lặp đi lặp lại một bài hát duy nhất.\n"
            "`!queue` - Xem danh sách các bài hát đang chờ phát.\n"
            "`!stop` - Dừng hẳn nhạc và để mình quay lại góc đọc sách."
        ),
        inline=False,
    )

    embed.add_field(
        name="🔮 **Trò Chuyện & Thảo Luận (AI)**",
        value="`!ai [nội dung]` - Trò chuyện, hỏi đáp hoặc tâm sự về sách, thơ văn với mình...",
        inline=False,
    )

    embed.set_footer(text="Cảm ơn bạn đã ghé thăm... Hãy pha một tách trà nóng và tận hưởng nhé.")
    await ctx.send(embed=embed)


# ================= 5. CÁC LỆNH ĐIỀU KHIỂN NHẠC =================


@bot.command(name="join")
async def join(ctx):
    if not ctx.author.voice:
        return await ctx.send("❌ Ứm... Bạn phải vào một Voice Channel trước thì mình mới tham gia được chứ...")
    channel = ctx.author.voice.channel
    if ctx.voice_client:
        await ctx.voice_client.move_to(channel)
    else:
        await ctx.voice_client.connect()
    await ctx.send(f"☕ Yuri đã lặng lẽ bước vào **{channel.name}**...")


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
            return await ctx.send("❌ X-Xin lỗi... Mình không thể đọc được dữ liệu từ liên kết SoundCloud này.")

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
                f"📝 Mình đã ghi chép lại bài **{song['title']}** vào danh sách chờ rồi nhé (Vị trí #{len(queues[guild_id])})."
            )
        else:
            ctx.voice_client.current_song = song
            source = discord.FFmpegPCMAudio(song["stream_url"], **FFMPEG_OPTIONS)
            ctx.voice_client.play(source, after=lambda e: check_queue_and_play(ctx))
            await ctx.send(f"☕ Đang phát nhạc giúp bạn nè... **{song['title']}**")


@bot.command(name="queue")
async def show_queue(ctx):
    guild_id = ctx.guild.id
    if guild_id not in queues or len(queues[guild_id]) == 0:
        return await ctx.send("📜 Hàng đợi hiện đang trống... Không có giai điệu nào tiếp theo cả.")

    msg = "**📜 Danh sách các giai điệu đang chờ:**\n"
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
        await ctx.send("⏭️ Đã bỏ qua bài hát hiện tại theo ý bạn...")
    else:
        await ctx.send("❌ Hiện tại đâu có bài hát nào đang phát đâu...")


@bot.command(name="pause")
async def pause(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸️ Đã tạm dừng giai điệu...")


@bot.command(name="resume")
async def resume(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("▶️ Tiếp tục giai điệu thôi nào.")


@bot.command(name="loop")
async def loop(ctx):
    guild_id = ctx.guild.id
    current = loop_status.get(guild_id, False)
    loop_status[guild_id] = not current
    status_str = "bật 🔂" if not current else "tắt ➡️"
    await ctx.send(f"Chế độ lặp lại bài hát đã được **{status_str}**.")


@bot.command(name="stop")
async def stop(ctx):
    guild_id = ctx.guild.id
    if guild_id in queues:
        queues[guild_id].clear()
    loop_status[guild_id] = False

    if ctx.voice_client:
        ctx.voice_client.stop()
        await ctx.voice_client.disconnect()
        await ctx.send("⏹️ Cảm ơn bạn. Mình xin phép về lại góc nhỏ đọc sách đây...")


# ================= 6. CÁC LỆNH TÍCH HỢP AI (YURI PERSONA - FIXED) =================


@bot.command(name="ai")
async def ai_chat(ctx, *, prompt: str):
    async with ctx.typing():
        # Chỉ dẫn tính cách cho Yuri (DDLC)
        system_instruction = (
            "Bạn là Yuri, một thành viên của Câu lạc bộ Văn học trong game Doki Doki Literature Club (DDLC).\n"
            "- Tính cách: Ngượng ngùng, rụt rè, cực kỳ lịch sự, dùng từ ngữ chau chuốt và trưởng thành. Thích đọc sách tiểu thuyết kinh dị/tâm lý phức tạp, thích pha trà đạo và bàn luận về thơ văn.\n"
            "- Cách nói chuyện: Đôi lúc ngập ngừng (dùng các từ như 'Ứm...', 'X-Xin lỗi...', 'Ít nhất là...'), trả lời sâu sắc, chu đáo.\n"
            "- Luôn giữ đúng vai nhân vật này trong suốt cuộc trò chuyện và xưng 'mình' hoặc 'Yuri' và gọi người dùng là 'bạn'."
        )
        
        try:
            # Gọi API Gemini chuẩn hóa không bị nghẽn
            response = ai_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config={"system_instruction": system_instruction}
            )
            await ctx.send(response.text)
        except Exception as e:
            print(f"[Error AI]: {e}")
            await ctx.send("💬 X-Xin lỗi bạn... Tâm trí mình đang hơi rối bời một chút nên chưa thể trả lời ngay được...")


# ================= 7. KHỞI CHẠY BOT VÀ FLASK =================


@bot.event
async def on_ready():
    print(f"✅ Yuri (DDLC Bot) đã sẵn sàng hoạt động dưới tên: {bot.user.name}")


if __name__ == "__main__":
    keep_alive()
    bot.run(DISCORD_TOKEN)
