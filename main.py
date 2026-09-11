import os
import asyncio
import collections
import random
import threading
from flask import Flask, jsonify
import discord
from discord.ext import commands
import google.generativeai as genai
import yt_dlp
import edge_tts
from dotenv import load_dotenv

# Nạp biến môi trường
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# --- 1. WEB SERVER FLASK (HEALTH CHECK) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Yuri Bot is alive and running smoothly!", 200

@app.route('/health')
def health():
    return jsonify({"status": "online", "bot": "Yuri", "version": "2.0"}), 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_flask, daemon=True).start()

# --- 2. CẤU HÌNH AI GEMINI ---
genai.configure(api_key=GEMINI_API_KEY)
yuri_model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    system_instruction=(
        "Bạn là Yuri từ câu lạc bộ văn học Doki Doki Literature Club. "
        "Tính cách: Dịu dàng, lịch sự, sâu sắc, hơi rụt rè nhưng cực kỳ đam mê văn học, "
        "tiểu thuyết kinh dị tâm lý và các câu chuyện có chiều sâu. "
        "Xưng hô: 'Tớ' hoặc 'Yuri' và gọi người dùng là 'Cậu' hoặc 'Tác giả'. "
        "Hãy trả lời bằng tiếng Việt tinh tế, trau chuốt và đậm chất văn học."
    )
)

# --- 3. CẤU HÌNH BOT DISCORD ---
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'extractflat': 'in_playlist',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'scsearch',
    'source_address': '0.0.0.0'
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

# Quản lý trạng thái nhạc
class GuildMusicState:
    def __init__(self):
        self.queue = collections.deque()
        self.current_track = None
        self.loop_mode = "off"  # "off", "track", "queue"
        self.autoplay = False
        self.last_query = None

music_states = {}

def get_music_state(guild_id: int) -> GuildMusicState:
    if guild_id not in music_states:
        music_states[guild_id] = GuildMusicState()
    return music_states[guild_id]

# --- 4. GIAO DIỆN TƯƠNG TÁC BUTTONS (MUSIC CONTROLLER VIEW) ---
class MusicControlView(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=None)
        self.ctx = ctx

    @discord.ui.button(label="Tạm dừng / Phát", style=discord.ButtonStyle.secondary, emoji="⏯️")
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = self.ctx.voice_client
        if not vc:
            return await interaction.response.send_message("Tớ không còn ở trong kênh thoại nữa...", ephemeral=True)
        if vc.is_playing():
            vc.pause()
            await interaction.response.send_message("⏸️ Đã tạm dừng nhạc.", ephemeral=True)
        elif vc.is_paused():
            vc.resume()
            await interaction.response.send_message("▶️ Tiếp tục phát nhạc.", ephemeral=True)

    @discord.ui.button(label="Bỏ qua", style=discord.ButtonStyle.primary, emoji="⏭️")
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = self.ctx.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
            await interaction.response.send_message("⏭️ Đã bỏ qua bài hiện tại.", ephemeral=True)
        else:
            await interaction.response.send_message("Không có bài hát nào đang phát.", ephemeral=True)

    @discord.ui.button(label="Lặp lại", style=discord.ButtonStyle.success, emoji="🔁")
    async def loop(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = get_music_state(self.ctx.guild.id)
        modes = ["off", "track", "queue"]
        next_mode = modes[(modes.index(state.loop_mode) + 1) % len(modes)]
        state.loop_mode = next_mode
        await interaction.response.send_message(f"🔁 Chế độ lặp lại: **{next_mode.upper()}**", ephemeral=True)

    @discord.ui.button(label="AutoPlay", style=discord.ButtonStyle.primary, emoji="🎲")
    async def autoplay(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = get_music_state(self.ctx.guild.id)
        state.autoplay = not state.autoplay
        status = "Bật" if state.autoplay else "Tắt"
        await interaction.response.send_message(f"🎲 AutoPlay SoundCloud: **{status}**", ephemeral=True)

    @discord.ui.button(label="Dừng & Rời", style=discord.ButtonStyle.danger, emoji="⏹️")
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = self.ctx.voice_client
        if vc:
            state = get_music_state(self.ctx.guild.id)
            state.queue.clear()
            state.current_track = None
            await vc.disconnect()
            await interaction.response.send_message("👋 Tớ đã dừng nhạc và rời kênh thoại.", ephemeral=True)

# --- 5. HỆ THỐNG LOGIC PHÁT NHẠC ---
async def play_next(ctx):
    state = get_music_state(ctx.guild.id)
    vc = ctx.voice_client

    if not vc or not vc.is_connected():
        return

    # Xử lý Lặp lại (Loop)
    if state.loop_mode == "track" and state.current_track:
        state.queue.appendleft(state.current_track)
    elif state.loop_mode == "queue" and state.current_track:
        state.queue.append(state.current_track)

    # Xử lý AutoPlay SoundCloud
    if len(state.queue) == 0 and state.autoplay and state.last_query:
        try:
            search_term = f"scsearch5:{state.last_query} radio"
            info = await asyncio.to_thread(lambda: ytdl.extract_info(search_term, download=False))
            if 'entries' in info and len(info['entries']) > 1:
                next_entry = info['entries'][random.randint(1, len(info['entries'])-1)]
                track = {
                    'title': next_entry.get('title', 'Unknown Track'),
                    'url': next_entry.get('url'),
                    'webpage_url': next_entry.get('webpage_url'),
                    'requester': 'Yuri AutoPlay'
                }
                state.queue.append(track)
        except Exception as e:
            print(f"AutoPlay error: {e}")

    if len(state.queue) == 0:
        state.current_track = None
        embed = discord.Embed(
            description="*Hàng đợi đã hết. Tớ xin phép không gian yên tĩnh này cho cậu nhé...*",
            color=discord.Color.dark_purple()
        )
        await ctx.send(embed=embed)
        return

    track = state.queue.popleft()
    state.current_track = track

    try:
        source = discord.FFmpegPCMAudio(track['url'], **FFMPEG_OPTIONS)
        vc.play(source, after=lambda e: bot.loop.create_task(play_next(ctx)))

        # EMBED TỰ ĐỘNG BẮT MẮT
        embed = discord.Embed(
            title="🎧 Đang Bật Nhạc Trên SoundCloud",
            description=f"**[{track['title']}]({track['webpage_url']})**",
            color=discord.Color.from_rgb(128, 0, 128)
        )
        embed.set_thumbnail(url="https://i.imgur.com/v8R2K2E.png") # Avatar hoạ tiết nhã nhặn
        embed.add_field(name="Người yêu cầu", value=f"`{track['requester']}`", inline=True)
        embed.add_field(name="Chế độ Loop", value=f"`{state.loop_mode.upper()}`", inline=True)
        embed.add_field(name="AutoPlay", value=f"`{'Bật' if state.autoplay else 'Tắt'}`", inline=True)
        embed.set_footer(text="Sử dụng các nút bên dưới để điều khiển trình phát nhạc")

        view = MusicControlView(ctx)
        await ctx.send(embed=embed, view=view)
    except Exception as e:
        await ctx.send(f"Đã xảy ra lỗi âm thanh: {e}")
        bot.loop.create_task(play_next(ctx))

# --- 6. SỰ KIỆN BOT ---
@bot.event
async def on_ready():
    print(f"=== Bot Yuri đã kích hoạt: {bot.user} ===")
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening, 
            name="trà và đọc tiểu thuyết cùng cậu | !help"
        )
    )

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if bot.user.mentioned_in(message) and not message.mention_everyone:
        clean_content = message.content.replace(f'<@{bot.user.id}>', '').strip()
        if clean_content:
            async with message.channel.typing():
                try:
                    response = yuri_model.generate_content(clean_content)
                    await message.reply(response.text)
                except Exception as e:
                    await message.reply("Ưm... Tớ xin lỗi, tâm trí tớ hơi xao nhãng. Cậu nói lại được không?")
            return

    await bot.process_commands(message)

# --- 7. CÁC LỆNH NHẠC NÂNG CAO ---
@bot.command(name="play", aliases=["p"])
async def play(ctx, *, query: str):
    """Phát nhạc SoundCloud"""
    if not ctx.author.voice:
        return await ctx.send("Cậu vào một Kênh thoại trước để tớ phát nhạc nhé!")

    vc = ctx.voice_client
    if not vc:
        vc = await ctx.author.voice.channel.connect()

    state = get_music_state(ctx.guild.id)
    state.last_query = query

    async with ctx.typing():
        search_query = query if query.startswith("http") else f"scsearch:{query}"
        info = await asyncio.to_thread(lambda: ytdl.extract_info(search_query, download=False))

        if 'entries' in info:
            info = info['entries'][0]

        track = {
            'title': info.get('title', 'Bài hát SoundCloud'),
            'url': info.get('url'),
            'webpage_url': info.get('webpage_url', query),
            'requester': ctx.author.display_name
        }

        state.queue.append(track)

        if not vc.is_playing() and not vc.is_paused():
            await play_next(ctx)
        else:
            embed = discord.Embed(
                description=f"🌸 Đã thêm vào hàng đợi: **[{track['title']}]({track['webpage_url']})**",
                color=discord.Color.purple()
            )
            await ctx.send(embed=embed)

@bot.command(name="shuffle")
async def shuffle(ctx):
    """Xáo trộn hàng đợi nhạc"""
    state = get_music_state(ctx.guild.id)
    if len(state.queue) < 2:
        return await ctx.send("Hàng đợi cần ít nhất 2 bài để xáo trộn chứ cậu.")
    
    random.shuffle(state.queue)
    await ctx.send("🔀 *Đã xáo trộn danh sách nhạc ngẫu nhiên!*")

@bot.command(name="queue", aliases=["q"])
async def queue(ctx):
    """Xem danh sách hàng đợi nhạc thiết kế thẩm mỹ"""
    state = get_music_state(ctx.guild.id)
    if not state.queue and not state.current_track:
        return await ctx.send("Hàng đợi hiện đang trống trải lắm...")

    embed = discord.Embed(
        title="📜 Danh Sách Nhạc Hàng Đợi",
        color=discord.Color.purple()
    )
    if state.current_track:
        embed.add_field(
            name="▶️ Đang phát", 
            value=f"**[{state.current_track['title']}]({state.current_track['webpage_url']})**", 
            inline=False
        )

    if state.queue:
        q_list = ""
        for idx, t in enumerate(state.queue, 1):
            if idx > 10:
                q_list += f"\n*...và {len(state.queue) - 10} bài hát khác.*"
                break
            q_list += f"**{idx}.** [{t['title']}]({t['webpage_url']}) - `{t['requester']}`\n"
        embed.add_field(name="📋 Tiếp theo", value=q_list, inline=False)
    
    await ctx.send(embed=embed)

# --- 8. TÍNH NĂNG ĐỌC SÁNG TÁC TIỂU THUYẾT & REVIEW SÁCH ---
@bot.command(name="doctieuthuyet", aliases=["novel"])
async def doctieuthuyet(ctx, *, description: str):
    """Sáng tác & Đọc truyện văn học vào Kênh thoại"""
    async with ctx.typing():
        prompt = (
            f"Hãy viết một câu chuyện ngắn khoảng 200-250 từ dựa trên chủ đề: '{description}'. "
            f"Văn phong tinh tế, sâu sắc, có chút cổ điển và đậm chất nghệ thuật tâm lý của Yuri. "
            f"Không thêm lời chào ngoài lề."
        )
        try:
            story_res = yuri_model.generate_content(prompt)
            story_text = story_res.text
        except Exception as e:
            return await ctx.send(f"Tớ chưa thể tập trung viết lách lúc này... Lỗi: {e}")

        # Gửi Embed tác phẩm
        embed = discord.Embed(
            title="📖 Tác Phẩm Do Yuri Sáng Tác",
            description=story_text,
            color=discord.Color.dark_purple()
        )
        embed.set_footer(text=f"Cảm hứng từ tác giả: {ctx.author.display_name}")
        await ctx.send(embed=embed)

        # Tạo file TTS với giọng đọc truyền cảm
        tts_file = f"story_{ctx.guild.id}.mp3"
        voice = "vi-VN-HoaiMyNeural"
        communicate = edge_tts.Communicate(story_text, voice)
        await communicate.save(tts_file)

        if not ctx.author.voice:
            return await ctx.send("*Tớ đã sáng tác xong câu chuyện. Nếu cậu vào Voice Channel, tớ có thể đọc trực tiếp cho cậu nghe đấy.*")

        vc = ctx.voice_client
        if not vc:
            vc = await ctx.author.voice.channel.connect()

        if vc.is_playing():
            vc.stop()

        def after_reading(error):
            if os.path.exists(tts_file):
                try:
                    os.remove(tts_file)
                except Exception:
                    pass

        source = discord.FFmpegPCMAudio(tts_file)
        vc.play(source, after=after_reading)
        await ctx.send("🎙️ *Yuri đang cất giọng đọc tác phẩm trong kênh thoại...*")

@bot.command(name="review")
async def review(ctx, *, book_name: str):
    """Cảm nhận và phân tích sâu sắc về tác phẩm/sách"""
    async with ctx.typing():
        prompt = f"Hãy đưa ra đánh giá, phân tích tâm lý sâu sắc và cảm nhận tinh tế về tác phẩm '{book_name}' dưới góc nhìn của Yuri."
        try:
            res = yuri_model.generate_content(prompt)
            embed = discord.Embed(
                title=f"📖 Cảm Nhận Văn Học: {book_name}",
                description=res.text,
                color=discord.Color.purple()
            )
            embed.set_footer(text="Góc nhìn văn học của Yuri")
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f"Ưm... Tớ chưa từng đọc qua cuốn này hoặc có lỗi xảy ra: {e}")

# --- 9. MENUS HƯỚNG DẪN BẮT MẮT ---
@bot.command(name="help")
async def help_command(ctx):
    embed = discord.Embed(
        title="✨ Sổ Tay Trí Tuệ & Văn Học - Yuri Bot",
        description="Chào cậu, tớ là Yuri. Rất vui được đồng hành cùng cậu qua những giai điệu SoundCloud và những trang sách.",
        color=discord.Color.purple()
    )
    embed.set_thumbnail(url="https://i.imgur.com/v8R2K2E.png")
    embed.add_field(
        name="🎵 Hệ Thống Âm Nhạc SoundCloud (Interactive)",
        value=(
            "• `!play <tên bài/link>`: Phát nhạc từ SoundCloud\n"
            "• `!shuffle`: Xáo trộn thứ tự hàng đợi\n"
            "• `!queue`: Xem danh sách chờ hiện tại\n"
            "*(Bot có sẵn các **Interactive Buttons** trực tiếp bên dưới tin nhắn nhạc)*"
        ),
        inline=False
    )
    embed.add_field(
        name="📖 Sáng Tác & Đọc Tiểu Thuyết AI",
        value=(
            "• `!doctieuthuyet <mô tả>`: Sáng tác văn học & cất giọng đọc TTS trong Voice\n"
            "• `!review <tên sách/manga>`: Phân tích và cảm nhận tác phẩm"
        ),
        inline=False
    )
    embed.add_field(
        name="💬 AI Trò Chuyện Tâm Sự",
        value="• Tag `@Yuri` + nội dung bất kỳ để tâm sự cùng tớ.",
        inline=False
    )
    await ctx.send(embed=embed)

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("Lỗi: Thiếu DISCORD_TOKEN trong biến môi trường!")
    else:
        bot.run(DISCORD_TOKEN)
