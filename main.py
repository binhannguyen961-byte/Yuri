import os
import asyncio
import collections
import random
import threading
import time
from flask import Flask, jsonify
import discord
from discord.ext import commands
import google.generativeai as genai
import yt_dlp
import edge_tts
from gtts import gTTS  # Thư viện Google Text-to-Speech
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
    return jsonify({"status": "online", "bot": "Yuri", "version": "2.1"}), 200

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

# Cho phép đọc thông tin Playlist bằng cách bỏ 'noplaylist': True
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'extractflat': 'in_playlist',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'nocheckcertificate': True,
    'ignoreerrors': True, # Bỏ qua bài hát lỗi trong playlist
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
        else:
            await interaction.response.send_message("Hiện không phát bài hát nào.", ephemeral=True)

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
            if info and 'entries' in info and len(info['entries']) > 1:
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
            description="*Hàng đợi đã hết. Tớ xin phép trả lại không gian yên tĩnh này cho cậu...*",
            color=discord.Color.dark_purple()
        )
        await ctx.send(embed=embed)
        return

    track = state.queue.popleft()
    state.current_track = track

    try:
        source = discord.FFmpegPCMAudio(track['url'], **FFMPEG_OPTIONS)
        
        def after_callback(error):
            if error:
                print(f"Lỗi phát nhạc: {error}")
            asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop)

        vc.play(source, after=after_callback)

        embed = discord.Embed(
            title="🎧 Đang Bật Nhạc Trên SoundCloud",
            description=f"**[{track['title']}]({track['webpage_url']})**",
            color=discord.Color.from_rgb(128, 0, 128)
        )
        embed.set_thumbnail(url="https://i.imgur.com/v8R2K2E.png")
        embed.add_field(name="Người yêu cầu", value=f"`{track['requester']}`", inline=True)
        embed.add_field(name="Chế độ Loop", value=f"`{state.loop_mode.upper()}`", inline=True)
        embed.add_field(name="AutoPlay", value=f"`{'Bật' if state.autoplay else 'Tắt'}`", inline=True)
        embed.set_footer(text="Sử dụng các nút bên dưới để điều khiển trình phát nhạc")

        view = MusicControlView(ctx)
        await ctx.send(embed=embed, view=view)
    except Exception as e:
        await ctx.send(f"Đã xảy ra lỗi âm thanh: {e}")
        asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop)

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

# --- 7. CÁC LỆNH NHẠC NÂNG CAO (HỖ TRỢ PLAYLIST) ---
@bot.command(name="play", aliases=["p"])
async def play(ctx, *, query: str):
    """Phát nhạc đơn hoặc Playlist từ SoundCloud/URL"""
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

        if not info:
            return await ctx.send("Tớ không tìm thấy bài hát hoặc danh sách nhạc phù hợp...")

        tracks_added = []
        
        # Xử lý nếu kết quả trả về là Playlist hoặc danh sách entries
        if 'entries' in info and info['entries']:
            # Nếu tìm kiếm bằng từ khóa thông thường, chỉ lấy bài đầu tiên
            if not query.startswith("http"):
                entries = [info['entries'][0]]
            else:
                entries = info['entries'] # Lấy toàn bộ Playlist

            for entry in entries:
                if not entry:
                    continue
                track = {
                    'title': entry.get('title', 'Bài hát SoundCloud'),
                    'url': entry.get('url'),
                    'webpage_url': entry.get('webpage_url', query),
                    'requester': ctx.author.display_name
                }
                state.queue.append(track)
                tracks_added.append(track)
        else:
            # Bài hát đơn lẻ
            track = {
                'title': info.get('title', 'Bài hát SoundCloud'),
                'url': info.get('url'),
                'webpage_url': info.get('webpage_url', query),
                'requester': ctx.author.display_name
            }
            state.queue.append(track)
            tracks_added.append(track)

        if len(tracks_added) == 0:
            return await ctx.send("Không trích xuất được bài hát nào từ đường dẫn.")

        if not vc.is_playing() and not vc.is_paused():
            await play_next(ctx)
        else:
            if len(tracks_added) == 1:
                embed = discord.Embed(
                    description=f"🌸 Đã thêm vào hàng đợi: **[{tracks_added[0]['title']}]({tracks_added[0]['webpage_url']})**",
                    color=discord.Color.purple()
                )
            else:
                embed = discord.Embed(
                    description=f"📚 Đã thêm **{len(tracks_added)} bài hát** từ Playlist vào hàng đợi!",
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
    """Xem danh sách hàng đợi nhạc"""
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

# --- 8. TÍNH NĂNG ĐÁNH GIÁ NHẠC & SÁNG TÁC TIỂU THUYẾT ---
@bot.command(name="danhgia", aliases=["rate", "reviewmusic"])
async def danhgia(ctx, *, query: str = None):
    """Yuri nhận xét và phân tích bài hát (Đang phát hoặc theo tên)"""
    state = get_music_state(ctx.guild.id)
    song_title = query

    if not song_title:
        if state.current_track:
            song_title = state.current_track['title']
        else:
            return await ctx.send("Cậu hãy nhập tên bài hát hoặc bật một bản nhạc để tớ thưởng thức và cảm nhận nhé!")

    async with ctx.typing():
        prompt = (
            f"Hãy đưa ra đánh giá, cảm nhận văn học tinh tế, phân tích giai điệu và "
            f"chấm điểm (trên thang điểm 10) cho bài hát/bản nhạc: '{song_title}'. "
            f"Giữ đúng tính cách dịu dàng, sâu sắc và đậm chất nghệ thuật của Yuri."
        )
        try:
            res = yuri_model.generate_content(prompt)
            embed = discord.Embed(
                title=f"🎵 Cảm Nhận Giai Điệu: {song_title}",
                description=res.text,
                color=discord.Color.dark_purple()
            )
            embed.set_footer(text=f"Đánh giá nghệ thuật bởi Yuri • Yêu cầu từ {ctx.author.display_name}")
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f"Ưm... Tâm trí tớ chưa thể cảm nhận bản nhạc này lúc này: {e}")

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
            return await ctx.send(f"Tớ chưa thể tập trung viết lách lúc me... Lỗi: {e}")

        embed = discord.Embed(
            title="📖 Tác Phẩm Do Yuri Sáng Tác",
            description=story_text,
            color=discord.Color.dark_purple()
        )
        embed.set_footer(text=f"Cảm hứng từ tác giả: {ctx.author.display_name}")
        await ctx.send(embed=embed)

        unique_id = int(time.time() * 1000)
        tts_file = f"story_{ctx.guild.id}_{unique_id}.mp3"
        voice = "vi-VN-HoaiMyNeural"
        communicate = edge_tts.Communicate(story_text, voice)
        await communicate.save(tts_file)

        if not ctx.author.voice:
            return await ctx.send("*Tớ đã sáng tác xong câu chuyện. Nếu cậu vào Voice Channel, tớ có thể đọc trực tiếp cho cậu nghe đấy.*")

        vc = ctx.voice_client
        if not vc:
            vc = await ctx.author.voice.channel.connect()

        if vc.is_playing():
            vc.pause()

        def after_reading(error):
            if os.path.exists(tts_file):
                try:
                    os.remove(tts_file)
                except Exception:
                    pass
            if vc and vc.is_paused():
                vc.resume()

        source = discord.FFmpegPCMAudio(tts_file)
        vc.play(source, after=after_reading)
        await ctx.send("🎙️ *Yuri đang cất giọng đọc tác phẩm trong kênh thoại...*")

# --- 9. LỆNH GOOGLE TEXT-TO-SPEECH (TIẾNG VIỆT) ---
@bot.command(name="tts", aliases=["noi", "say"])
async def tts_command(ctx, *, text: str):
    """Phát lại văn bản người dùng nhập bằng giọng Google TTS Tiếng Việt"""
    if not ctx.author.voice:
        return await ctx.send("Cậu vào Kênh thoại trước để tớ cất giọng đọc cho cậu nghe nhé!")

    vc = ctx.voice_client
    if not vc:
        vc = await ctx.author.voice.channel.connect()

    is_music_paused = False
    if vc.is_playing():
        vc.pause()
        is_music_paused = True

    async with ctx.typing():
        unique_id = int(time.time() * 1000)
        tts_file = f"gtts_{ctx.guild.id}_{unique_id}.mp3"

        try:
            # Tạo file âm thanh bằng Google Text-to-Speech tiếng Việt (lang='vi')
            tts = gTTS(text=text, lang='vi')
            tts.save(tts_file)

            def after_speaking(error):
                if os.path.exists(tts_file):
                    try:
                        os.remove(tts_file)
                    except Exception:
                        pass
                # Nếu nhạc từng bị tạm dừng để nhường giọng đọc, tiếp tục phát lại
                if is_music_paused and vc and vc.is_paused():
                    vc.resume()

            source = discord.FFmpegPCMAudio(tts_file)
            vc.play(source, after=after_speaking)
            await ctx.send(f"🗣️ *Yuri cất lời:* \"{text}\"")
        except Exception as e:
            await ctx.send(f"Đã xảy ra lỗi khi phát giọng nói: {e}")
            if is_music_paused and vc and vc.is_paused():
                vc.resume()

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

# --- 10. MENUS HƯỚNG DẪN BẮT MẮT ---
@bot.command(name="help")
async def help_command(ctx):
    embed = discord.Embed(
        title="✨ Sổ Tay Trí Tuệ & Văn Học - Yuri Bot",
        description="Chào cậu, tớ là Yuri. Rất vui được đồng hành cùng cậu qua những giai điệu SoundCloud và những trang sách.",
        color=discord.Color.purple()
    )
    embed.set_thumbnail(url="https://i.imgur.com/v8R2K2E.png")
    embed.add_field(
        name="🎵 Hệ Thống Âm Nhạc & Đánh Giá",
        value=(
            "• `!play <tên bài/link playlist>`: Phát nhạc/Playlist từ SoundCloud\n"
            "• `!danhgia [tên bài]`: Yuri phân tích & chấm điểm bản nhạc\n"
            "• `!shuffle`: Xáo trộn thứ tự hàng đợi nhạc\n"
            "• `!queue`: Xem danh sách chờ hiện tại"
        ),
        inline=False
    )
    embed.add_field(
        name="🗣️ Google Text-To-Speech",
        value="• `!tts <văn bản>` hoặc `!noi <văn bản>`: Yuri phát giọng Google Việt Nam trong kênh thoại.",
        inline=False
    )
    embed.add_field(
        name="📖 Sáng Tác & Văn Học AI",
        value=(
            "• `!doctieuthuyet <mô tả>`: Sáng tác văn học & đọc TTS giọng Hoài Mỹ\n"
            "• `!review <tên sách>`: Phân tích cảm nhận tác phẩm"
        ),
        inline=False
    )
    embed.add_field(
        name="💬 AI Trò Chuyện",
        value="• Tag `@Yuri` + nội dung bất kỳ để tâm sự cùng tớ.",
        inline=False
    )
    await ctx.send(embed=embed)

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("Lỗi: Thiếu DISCORD_TOKEN trong biến môi trường!")
    else:
        bot.run(DISCORD_TOKEN)
