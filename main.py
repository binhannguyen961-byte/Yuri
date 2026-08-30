import asyncio
import os
import threading
import discord
from discord.ext import commands
from flask import Flask
from google import genai
from google.genai import types
import yt_dlp

# ================= 1. CẤU HÌNH WEB SERVER (FLASK) =================
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
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ================= 3. CẤU HÌNH PHÁT NHẠC & QUẢN LÝ VOICE =================
YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "extractflat": True,
    "noplaylist": False,
    "quiet": True,
}

FFMPEG_OPTIONS = {
    "before_options": (
        "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
    ),
    "options": "-vn",
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)
queues = {}
loop_status = {}
auto_disconnect_tasks = {}


async def auto_stop_after_timeout(ctx, delay=300):
  """Hàm chờ 5 phút để ngắt voice nếu phòng trống"""
  await asyncio.sleep(delay)
  guild_id = ctx.guild.id

  if ctx.voice_client:
    members = [m for m in ctx.voice_client.channel.members if not m.bot]
    if len(members) == 0:
      if guild_id in queues:
        queues[guild_id].clear()
      loop_status[guild_id] = False
      if ctx.voice_client.is_playing() or ctx.voice_client.is_paused():
        ctx.voice_client.stop()
      await ctx.voice_client.disconnect()
      await ctx.send(
          "⌛ **Không có ai trong phòng voice quá 5 phút, Yuri xin phép rời"
          " phòng và dừng phát nhạc nhé...**"
      )

  if guild_id in auto_disconnect_tasks:
    del auto_disconnect_tasks[guild_id]


def check_queue_and_play(ctx):
  guild_id = ctx.guild.id

  # 1. KIỂM TRA SỐ LƯỢNG THÀNH VIÊN TRONG VOICE
  if ctx.voice_client and ctx.voice_client.channel:
    members = [m for m in ctx.voice_client.channel.members if not m.bot]

    if len(members) == 0:
      if guild_id not in auto_disconnect_tasks:
        asyncio.run_coroutine_threadsafe(
            ctx.send(
                "😴 Không có ai trong phòng voice... Yuri sẽ tạm ngưng và tự"
                " rời phòng sau **5 phút** nếu không có ai quay lại."
            ),
            bot.loop,
        )
        task = asyncio.run_coroutine_threadsafe(
            auto_stop_after_timeout(ctx, 300), bot.loop
        )
        auto_disconnect_tasks[guild_id] = task
      return
    else:
      if guild_id in auto_disconnect_tasks:
        auto_disconnect_tasks[guild_id].cancel()
        del auto_disconnect_tasks[guild_id]

  # 2. XỬ LÝ LẶP BÀI HOẶC CHUYỂN BÀI
  if loop_status.get(guild_id, False) and hasattr(
      ctx.voice_client, "current_song"
  ):
    song = ctx.voice_client.current_song
  elif guild_id in queues and len(queues[guild_id]) > 0:
    song = queues[guild_id].pop(0)
    ctx.voice_client.current_song = song
  else:
    ctx.voice_client.current_song = None
    return

  async def play_async():
    try:
      info = await bot.loop.run_in_executor(
          None,
          lambda: yt_dlp.YoutubeDL({"format": "bestaudio/best"}).extract_info(
              song["webpage_url"], download=False
          ),
      )
      stream_target = info["url"]

      # Dùng FFmpeg chuẩn từ hệ thống Railway (thông qua nixpacks.toml)
      source = discord.FFmpegPCMAudio(stream_target, **FFMPEG_OPTIONS)

      ctx.voice_client.play(source, after=lambda e: check_queue_and_play(ctx))
      await ctx.send(f"☕ Đang phát nhạc giúp bạn nè... **{song['title']}**")
    except Exception as e:
      await ctx.send(
          f"⚠️ **Không thể phát bài {song.get('title', '')}:** `{e}`. Đang thử"
          " chuyển bài tiếp theo..."
      )
      check_queue_and_play(ctx)

  asyncio.run_coroutine_threadsafe(play_async(), bot.loop)


# ================= 4. EVENT THEO DÕI VOICE STATE =================
@bot.event
async def on_voice_state_update(member, before, after):
  if member.bot:
    return

  for voice_client in bot.voice_clients:
    guild_id = voice_client.guild.id
    channel = voice_client.channel
    members = [m for m in channel.members if not m.bot]

    if len(members) == 0:
      if guild_id not in auto_disconnect_tasks:
        task = asyncio.create_task(
            auto_stop_after_timeout(
                await bot.get_context(
                    await channel.send(
                        "😴 Mọi người đã rời phòng voice. Yuri sẽ tự ngắt"
                        " kết nối sau **5 phút**..."
                    )
                ),
                300,
            )
        )
        auto_disconnect_tasks[guild_id] = task
    else:
      if guild_id in auto_disconnect_tasks:
        auto_disconnect_tasks[guild_id].cancel()
        del auto_disconnect_tasks[guild_id]


# ================= 5. LỆNH HELP (!Yhelps) =================
@bot.command(name="Yhelps")
async def custom_help(ctx):
  embed = discord.Embed(
      title="📖 Câu Lạc Bộ Văn Học - Sổ Tay Hướng Dẫn Của Yuri",
      description=(
          "X-Xin lỗi vì làm phiền... Dưới đây là các lệnh bạn có thể dùng:"
      ),
      color=discord.Color.from_rgb(108, 52, 131),
  )
  embed.add_field(
      name="🎶 **Âm Nhạc (Hỗ trợ SoundCloud & Playlist)**",
      value=(
          "`!join` - Mời bot vào voice\n"
          "`!play [link/playlist]` - Phát nhạc hoặc cả Playlist\n"
          "`!pause` | `!resume` | `!skip` | `!loop` | `!queue` | `!stop`"
      ),
      inline=False,
  )
  embed.add_field(
      name="🔮 **Trò Chuyện AI**",
      value="`!ai [nội dung]` - Trò chuyện với Yuri (Gemini 3.6 Flash)",
      inline=False,
  )
  await ctx.send(embed=embed)


# ================= 6. CÁC LỆNH PHÁT NHẠC =================
@bot.command(name="join")
async def join(ctx):
  if not ctx.author.voice:
    return await ctx.send("❌ Bạn phải vào phòng Voice Channel trước nhé...")

  channel = ctx.author.voice.channel
  try:
    if ctx.voice_client:
      await ctx.voice_client.move_to(channel)
    else:
      await channel.connect()
    await ctx.send(f"☕ Yuri đã vào **{channel.name}**...")
  except Exception as e:
    await ctx.send(f"⚠️ **Không thể kết nối Voice Channel:** `{e}`")


@bot.command(name="play")
async def play(ctx, url: str):
  if not ctx.voice_client:
    await ctx.invoke(join)
    if not ctx.voice_client:
      return

  async with ctx.typing():
    try:
      data = await bot.loop.run_in_executor(
          None, lambda: ytdl.extract_info(url, download=False)
      )
    except Exception as e:
      return await ctx.send(
          f"❌ Không thể lấy thông tin bài hát/playlist: `{e}`"
      )

    guild_id = ctx.guild.id
    if guild_id not in queues:
      queues[guild_id] = []

    # XỬ LÝ PLAYLIST
    if "entries" in data and len(data["entries"]) > 0:
      playlist_title = data.get("title", "Playlist")
      added_count = 0

      for entry in data["entries"]:
        if entry:
          raw_url = (
              entry.get("webpage_url")
              or entry.get("url")
              or entry.get("permalink_url")
          )
          if raw_url:
            if not raw_url.startswith("http"):
              song_url = f"https://soundcloud.com/{raw_url.lstrip('/')}"
            else:
              song_url = raw_url

            song_title = entry.get("title", "Bài hát không tên")
            queues[guild_id].append(
                {"webpage_url": song_url, "title": song_title}
            )
            added_count += 1

      if not ctx.voice_client.is_playing() and not ctx.voice_client.is_paused():
        check_queue_and_play(ctx)
        await ctx.send(
            f"🎶 Đã thêm **{added_count}** bài từ playlist **{playlist_title}**"
            " vào danh sách phát."
        )
      else:
        await ctx.send(
            f"📝 Đã thêm **{added_count}** bài hát từ playlist"
            f" **{playlist_title}** vào hàng đợi."
        )

    # XỬ LÝ BÀI HÁT ĐƠN LẺ
    else:
      song_url = data.get("webpage_url") or data.get("url") or url
      song = {
          "webpage_url": song_url,
          "title": data.get("title", "Bài hát không tên"),
      }

      if ctx.voice_client.is_playing() or ctx.voice_client.is_paused():
        queues[guild_id].append(song)
        await ctx.send(
            f"📝 Đã thêm **{song['title']}** vào danh sách chờ"
            f" (#{len(queues[guild_id])})."
        )
      else:
        queues[guild_id].insert(0, song)
        check_queue_and_play(ctx)


@bot.command(name="queue")
async def show_queue(ctx):
  guild_id = ctx.guild.id
  if guild_id not in queues or len(queues[guild_id]) == 0:
    return await ctx.send("📜 Hàng đợi hiện đang trống.")
  msg = "**📜 Danh sách bài hát chờ:**\n"
  for idx, song in enumerate(queues[guild_id], start=1):
    msg += f"`{idx}.` {song['title']}\n"
    if idx >= 25:
      msg += f"...và còn {len(queues[guild_id]) - 25} bài nữa."
      break
  await ctx.send(msg)


@bot.command(name="skip")
async def skip(ctx):
  if ctx.voice_client and (
      ctx.voice_client.is_playing() or ctx.voice_client.is_paused()
  ):
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
    await ctx.send("▶️ Tiếp tục phát nhạc.")


@bot.command(name="loop")
async def loop(ctx):
  guild_id = ctx.guild.id
  current = loop_status.get(guild_id, False)
  loop_status[guild_id] = not current
  await ctx.send(f"Lặp lại bài hiện tại: **{'Bật' if not current else 'Tắt'}**.")


@bot.command(name="stop")
async def stop(ctx):
  guild_id = ctx.guild.id
  if guild_id in queues:
    queues[guild_id].clear()
  loop_status[guild_id] = False

  if guild_id in auto_disconnect_tasks:
    auto_disconnect_tasks[guild_id].cancel()
    del auto_disconnect_tasks[guild_id]

  if ctx.voice_client:
    ctx.voice_client.stop()
    await ctx.voice_client.disconnect()
    await ctx.send("⏹️ Đã dừng phát và rời phòng.")


# ================= 7. LỆNH AI GEMINI (CỐ ĐỊNH 3.6 FLASH) =================
@bot.command(name="ai")
async def ai_chat(ctx, *, prompt: str):
  async with ctx.typing():
    system_instruction = (
        "Bạn là Yuri trong Doki Doki Literature Club. "
        "Trả lời ngượng ngùng, rụt rè, hướng nội và cực kỳ lịch sự, từ ngữ chau"
        " chuốt, ngắn gọn. Xưng 'mình' hoặc 'tớ' hay 'Yuri', gọi người dùng là"
        " 'cậu'."
    )

    config = types.GenerateContentConfig(system_instruction=system_instruction)

    try:
      response = await bot.loop.run_in_executor(
          None,
          lambda: ai_client.models.generate_content(
              model="gemini-3.6-flash", contents=prompt, config=config
          ),
      )

      if response and hasattr(response, "text") and response.text:
        reply_text = response.text
        if len(reply_text) > 1900:
          for chunk in [
              reply_text[i : i + 1900] for i in range(0, len(reply_text), 1900)
          ]:
            await ctx.send(chunk)
        else:
          await ctx.send(reply_text)
      else:
        await ctx.send(
            "💬 X-Xin lỗi bạn... Tâm trí mình đang hơi rối bời một chút nên chưa"
            " thể trả lời ngay được..."
        )

    except Exception as e:
      await ctx.send(
          f"💬 X-Xin lỗi bạn... Có lỗi xảy ra khi gọi AI:\n`Chi tiết: {e}`"
      )


# ================= 8. KHI BOT SẴN SÀNG =================
@bot.event
async def on_ready():
  print(f"✅ Bot Yuri đã hoạt động: {bot.user.name}")


if __name__ == "__main__":
  keep_alive()
  bot.run(DISCORD_TOKEN)
