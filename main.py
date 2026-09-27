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
from gtts import gTTS
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
        "Tính cách: Dịu dàng, lịch sự, sâu sắc, hơi rụt rè nhưng cực kỳ đam mê văn học. "
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
    'nocheckcertificate': True,
    'ignoreerrors': True,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'scsearch',
    'source_address': '0.0.0.0'
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

# Quản lý trạng thái nhạc
class GuildMusicState:
    def __init__(self):
        self.queue = collections.deque()
        self.current_track = None
        self.loop_mode = "off"
        self.autoplay = False
        self.last_query = None
        self.volume = 1.0  # Mặc định âm lượng 100%

music_states = {}

def get_music_state(guild_id: int) -> GuildMusicState:
    if guild_id not in music_states:
        music_states[guild_id] = GuildMusicState()
    return music_states[guild_id]

# --- 4. GIAO DIỆN TƯƠNG TÁC THỜI GIAN THỰC ---
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

    @discord.ui.button(label="Lặp lại", style=discord.ButtonStyle.success, emoji="🔁")
    async def loop(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = get_music_state(self.ctx.guild.id)
        modes = ["off", "track", "queue"]
        state.loop_mode = modes[(modes.index(state.loop_mode) + 1) % len(modes)]
        
        vc = self.ctx.voice_client
        # Nếu bật loop hàng đợi mà nhạc vừa tắt, kích hoạt ngay lại play_next
        if state.loop_mode != "off" and vc and not vc.is_playing() and len(state.queue) == 0 and state.current_track:
            bot.loop.create_task(play_next(self.ctx))
            
        await interaction.response.send_message(f"🔁 Chế độ lặp lại: **{state.loop_mode.upper()}**", ephemeral=True)

    @discord.ui.button(label="AutoPlay", style=discord.ButtonStyle.primary, emoji="🎲")
    async def autoplay(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = get_music_state(self.ctx.guild.id)
        state.autoplay = not state.autoplay
        status = "Bật" if state.autoplay else "Tắt"
        
        vc = self.ctx.voice_client
        # THỜI GIAN THỰC: Nếu bật Autoplay mà nhạc đang trống, tự động tìm và phát luôn
        if state.autoplay and vc and not vc.is_playing() and not vc.is_paused() and len(state.queue) == 0:
            bot.loop.create_task(play_next(self.ctx))
            
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

# --- 5. LOGIC PHÁT NHẠC CƠ BẢN ---
async def play_next(ctx):
    state = get_music_state(ctx.guild.id)
    vc = ctx.voice_client

    if not vc or not vc.is_connected():
        return

    # Xử lý Lặp lại
    if state.loop_mode == "track" and state.current_track:
        state.queue.appendleft(state.current_track)
    elif state.loop_mode == "queue" and state.current_track:
        state.queue.append(state.current_track)

    # Xử lý AutoPlay
    if len(state.queue) == 0 and state.autoplay and state.last_query:
        try:
            search_term = f"scsearch5:{state.last_query} radio"
            info = await asyncio.to_thread(lambda: ytdl.extract_info(search_term, download=False))
            if info and 'entries' in info and len(info['entries']) > 1:
                next_entry = info['entries'][random.randint(1, len(info['entries'])-1)]
                state.queue.append({
                    'title': next_entry.get('title', 'Unknown Track'),
                    'url': next_entry.get('url'),
                    'webpage_url': next_entry.get('webpage_url'),
                    'requester': 'Yuri AutoPlay'
                })
        except Exception:
            pass

    if len(state.queue) == 0:
        state.current_track = None
        return await ctx.send(embed=discord.Embed(description="*Hàng đợi đã hết. Tớ xin phép trả lại không gian yên tĩnh...*", color=discord.Color.dark_purple()))

    track = state.queue.popleft()
    state.current_track = track

    try:
        ffmpeg_opts = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn'
        }
        
        source = discord.FFmpegPCMAudio(track['url'], **ffmpeg_opts)
        # Bọc âm thanh qua PCMVolumeTransformer để áp dụng mức âm lượng
        source = discord.PCMVolumeTransformer(source, volume=state.volume)
        
        def after_callback(error):
            asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop)

        vc.play(source, after=after_callback)

        embed = discord.Embed(
            title="🎧 Đang Bật Nhạc",
            description=f"**[{track['title']}]({track['webpage_url']})**",
            color=discord.Color.purple()
        )
        embed.set_thumbnail(url="https://i.imgur.com/v8R2K2E.png")
        embed.add_field(name="AutoPlay", value=f"`{'Bật' if state.autoplay else 'Tắt'}`", inline=True)
        embed.add_field(name="Âm lượng", value=f"`{int(state.volume * 100)}%`", inline=True)
        
        await ctx.send(embed=embed, view=MusicControlView(ctx))
    except Exception as e:
        await ctx.send(f"Đã xảy ra lỗi âm thanh: {e}")
        bot.loop.create_task(play_next(ctx))

# --- 6. SỰ KIỆN BOT ---
@bot.event
async def on_ready():
    print(f"=== Bot Yuri đã kích hoạt: {bot.user} ===")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="!Yhelps"))

# --- 7. CÁC LỆNH BOT ---

@bot.command(name="vol", aliases=["volume"])
async def set_volume(ctx, vol: int):
    """Chỉnh âm lượng bot (Mỗi nấc 25%)"""
    if vol not in [25, 50, 75, 100]:
        return await ctx.send("Cậu vui lòng chọn mức âm lượng: **25, 50, 75, hoặc 100** nhé.")
    
    state = get_music_state(ctx.guild.id)
    state.volume = vol / 100.0
    
    vc = ctx.voice_client
    if vc and vc.source and isinstance(vc.source, discord.PCMVolumeTransformer):
        vc.source.volume = state.volume
        
    await ctx.send(f"🔊 Yuri đã chỉnh âm lượng xuống mức **{vol}%** rồi đấy.")

@bot.command(name="play", aliases=["p"])
async def play(ctx, *, query: str):
    """Phát nhạc SoundCloud"""
    if not ctx.author.voice:
        return await ctx.send("Cậu vào một Kênh thoại trước nhé!")
    vc = ctx.voice_client or await ctx.author.voice.channel.connect()

    state = get_music_state(ctx.guild.id)
    state.last_query = query
    async with ctx.typing():
        search_query = query if query.startswith("http") else f"scsearch:{query}"
        info = await asyncio.to_thread(lambda: ytdl.extract_info(search_query, download=False))
        if not info: return await ctx.send("Tớ không tìm thấy bài hát...")

        entries = info['entries'] if 'entries' in info and query.startswith("http") else [info['entries'][0] if 'entries' in info else info]
        for entry in entries:
            if not entry: continue
            state.queue.append({'title': entry.get('title'), 'url': entry.get('url'), 'webpage_url': entry.get('webpage_url', query), 'requester': ctx.author.display_name})

        if not vc.is_playing() and not vc.is_paused():
            await play_next(ctx)
        else:
            await ctx.send(f"🌸 Đã thêm **{len(entries)}** bài vào hàng đợi.")

@bot.command(name="oneshot")
async def oneshot(ctx, *, prompt: str):
    """Yuri sáng tác một truyện ngắn (oneshot) trực tiếp trên khung chat"""
    async with ctx.typing():
        full_prompt = (
            f"Hãy sáng tác một truyện ngắn (oneshot) thật trọn vẹn, sâu sắc, phong cách văn học về chủ đề: '{prompt}'. "
            f"Góc nhìn của Yuri, không quá dài nhưng phải có mở đầu, cao trào và kết thúc lắng đọng."
        )
        try:
            res = yuri_model.generate_content(full_prompt)
            embed = discord.Embed(title="🖋️ Tác Phẩm Oneshot Của Yuri", description=res.text, color=discord.Color.purple())
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send("Tâm trí tớ đang xao nhãng, chưa thể viết lúc này...")

@bot.command(name="doctieuthuyet")
async def doctieuthuyet(ctx, *, args: str):
    """Cú pháp: !doctieuthuyet Nội dung truyện | Link bài nhạc"""
    if not ctx.author.voice:
        return await ctx.send("Cậu hãy vào kênh thoại để tớ đọc cho nghe nhé.")
    vc = ctx.voice_client or await ctx.author.voice.channel.connect()
    
    parts = args.split("|")
    story_prompt = parts[0].strip()
    bgm_link = parts[1].strip() if len(parts) > 1 else None

    async with ctx.typing():
        # 1. Sáng tác truyện
        res = yuri_model.generate_content(f"Viết 1 đoạn truyện 200 từ thật sâu sắc về: {story_prompt}")
        story_text = res.text
        await ctx.send(embed=discord.Embed(title="📖 Đang đọc tác phẩm", description=story_text, color=discord.Color.dark_purple()))

        # 2. Tạo TTS
        unique_id = int(time.time() * 1000)
        tts_file = f"story_{ctx.guild.id}_{unique_id}.mp3"
        await edge_tts.Communicate(story_text, "vi-VN-HoaiMyNeural").save(tts_file)

        # 3. Kết hợp nhạc nền bằng filter của FFmpeg (amix)
        if vc.is_playing(): vc.stop()

        def cleanup_and_resume(error):
            if os.path.exists(tts_file): os.remove(tts_file)
            asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop)

        if bgm_link:
            info = await asyncio.to_thread(lambda: ytdl.extract_info(bgm_link, download=False))
            bgm_url = info['url'] if 'url' in info else info['entries'][0]['url']
            
            # Giải thích FFmpeg: Input 0 là file TTS, Input 1 là Nhạc (bgm_url). Mix 2 cái lại, giảm âm lượng input 1 xuống 0.25
            ffmpeg_opts = {
                'before_options': f'-i "{tts_file}" -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
                'options': '-vn -filter_complex "[0:a]volume=1.0[tts];[1:a]volume=0.25[bgm];[tts][bgm]amix=inputs=2:duration=first"'
            }
            source = discord.FFmpegPCMAudio(bgm_url, **ffmpeg_opts)
            await ctx.send("🎙️ *Yuri bắt đầu đọc truyện với nhạc nền du dương...*")
        else:
            source = discord.FFmpegPCMAudio(tts_file)
            await ctx.send("🎙️ *Yuri đang cất giọng đọc tác phẩm...*")

        vc.play(source, after=cleanup_and_resume)

@bot.command(name="Yhelps")
async def yhelps(ctx):
    """Bảng hiển thị toàn bộ lệnh"""
    embed = discord.Embed(title="✨ Sổ Tay Lệnh Của Yuri", color=discord.Color.purple())
    embed.add_field(name="🎵 Nhạc", value="`!play <link>`: Bật nhạc\n`!vol <25/50/75/100>`: Chỉnh âm lượng", inline=False)
    embed.add_field(name="📖 Văn Học", value="`!oneshot <chủ đề>`: Yuri viết truyện ngắn tại chat\n`!doctieuthuyet <chủ đề> | <link nhạc>`: Đọc truyện & mix nhạc nền tự động", inline=False)
    embed.add_field(name="💬 Khác", value="`!tts <chữ>`: Giọng Google Việt Nam\nTag `@Yuri` để trò chuyện", inline=False)
    await ctx.send(embed=embed)

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
