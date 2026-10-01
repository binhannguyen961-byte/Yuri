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
    model_name="gemini-3.6-flash",
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

# Quản lý trạng thái nhạc & tính năng
class GuildState:
    def __init__(self):
        self.queue = collections.deque()
        self.current_track = None
        self.loop_mode = "off"
        self.autoplay = False
        self.last_query = None
        self.volume = 1.0  
        self.fakevoice_target = None # Lưu ID người bị nhại giọng

states = {}

def get_state(guild_id: int) -> GuildState:
    if guild_id not in states:
        states[guild_id] = GuildState()
    return states[guild_id]

# --- 4. GIAO DIỆN TƯƠNG TÁC THỜI GIAN THỰC ---
class MusicControlView(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=None)
        self.ctx = ctx

    @discord.ui.button(label="Tạm dừng / Phát", style=discord.ButtonStyle.secondary, emoji="⏯️")
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = self.ctx.voice_client
        if not vc: return await interaction.response.send_message("Tớ không ở trong kênh thoại...", ephemeral=True)
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
        state = get_state(self.ctx.guild.id)
        modes = ["off", "track", "queue"]
        state.loop_mode = modes[(modes.index(state.loop_mode) + 1) % len(modes)]
        
        vc = self.ctx.voice_client
        if state.loop_mode != "off" and vc and not vc.is_playing() and len(state.queue) == 0 and state.current_track:
            bot.loop.create_task(play_next(self.ctx))
            
        await interaction.response.send_message(f"🔁 Chế độ lặp lại: **{state.loop_mode.upper()}**", ephemeral=True)

    @discord.ui.button(label="AutoPlay", style=discord.ButtonStyle.primary, emoji="🎲")
    async def autoplay(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = get_state(self.ctx.guild.id)
        state.autoplay = not state.autoplay
        
        vc = self.ctx.voice_client
        if state.autoplay and vc and not vc.is_playing() and not vc.is_paused() and len(state.queue) == 0:
            bot.loop.create_task(play_next(self.ctx))
            
        await interaction.response.send_message(f"🎲 AutoPlay SoundCloud: **{'Bật' if state.autoplay else 'Tắt'}**", ephemeral=True)

    @discord.ui.button(label="Dừng & Rời", style=discord.ButtonStyle.danger, emoji="⏹️")
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = self.ctx.voice_client
        if vc:
            state = get_state(self.ctx.guild.id)
            state.queue.clear()
            state.current_track = None
            await vc.disconnect()
            await interaction.response.send_message("👋 Tớ đã dừng nhạc và rời kênh thoại.", ephemeral=True)

# --- 5. LOGIC PHÁT NHẠC ---
async def play_next(ctx):
    state = get_state(ctx.guild.id)
    vc = ctx.voice_client

    if not vc or not vc.is_connected(): return

    if state.loop_mode == "track" and state.current_track:
        state.queue.appendleft(state.current_track)
    elif state.loop_mode == "queue" and state.current_track:
        state.queue.append(state.current_track)

    if len(state.queue) == 0 and state.autoplay and state.last_query:
        try:
            info = await asyncio.to_thread(lambda: ytdl.extract_info(f"scsearch5:{state.last_query} radio", download=False))
            if info and 'entries' in info and len(info['entries']) > 1:
                next_entry = random.choice(info['entries'][1:])
                state.queue.append({
                    'title': next_entry.get('title', 'Unknown'),
                    'url': next_entry.get('url'),
                    'webpage_url': next_entry.get('webpage_url'),
                    'requester': 'Yuri AutoPlay'
                })
        except Exception: pass

    if len(state.queue) == 0:
        state.current_track = None
        return

    track = state.queue.popleft()
    state.current_track = track

    try:
        ffmpeg_opts = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}
        source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(track['url'], **ffmpeg_opts), volume=state.volume)
        
        vc.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop))

        embed = discord.Embed(
            title="🎧 Đang Bật Nhạc",
            description=f"**[{track['title']}]({track['webpage_url']})**",
            color=discord.Color.purple()
        )
        embed.set_thumbnail(url="https://i.imgur.com/v8R2K2E.png")
        embed.add_field(name="Yêu cầu", value=f"`{track['requester']}`", inline=True)
        embed.add_field(name="AutoPlay", value=f"`{'Bật' if state.autoplay else 'Tắt'}**", inline=True)
        embed.add_field(name="Âm lượng", value=f"`{int(state.volume * 100)}%`", inline=True)
        
        await ctx.send(embed=embed, view=MusicControlView(ctx))
    except Exception as e:
        bot.loop.create_task(play_next(ctx))

# --- 6. SỰ KIỆN BOT VÀ TÍNH NĂNG FAKEVOICE (PARROT MODE) ---
@bot.event
async def on_ready():
    print(f"=== Bot Yuri đã kích hoạt: {bot.user} ===")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="!Yhelps"))

@bot.event
async def on_message(message):
    if message.author.bot: return

    # Xử lý Fakevoice (Nhại lại nội dung người dùng gõ bằng TTS)
    state = get_state(message.guild.id)
    if state.fakevoice_target == message.author.id and message.content and not message.content.startswith("!"):
        vc = message.guild.voice_client
        if vc and not vc.is_playing():
            unique_id = int(time.time() * 1000)
            tts_file = f"fakevoice_{message.guild.id}_{unique_id}.mp3"
            try:
                gTTS(text=message.content, lang='vi').save(tts_file)
                source = discord.FFmpegPCMAudio(tts_file)
                vc.play(source, after=lambda e: os.remove(tts_file) if os.path.exists(tts_file) else None)
            except Exception: pass

    # Xử lý trò chuyện với AI
    if bot.user.mentioned_in(message) and not message.mention_everyone:
        clean_content = message.content.replace(f'<@{bot.user.id}>', '').strip()
        if clean_content:
            async with message.channel.typing():
                try: await message.reply(yuri_model.generate_content(clean_content).text)
                except Exception: await message.reply("Tâm trí tớ đang xao nhãng...")
            return

    await bot.process_commands(message)

# --- 7. CÁC LỆNH BOT ---
@bot.command(name="fakevoice", aliases=["nhai"])
async def fakevoice(ctx, member: discord.Member = None):
    """Bật/Tắt chế độ nhại lại lời nói qua Chat -> TTS"""
    state = get_state(ctx.guild.id)
    if not member:
        state.fakevoice_target = None
        return await ctx.send("🔇 Tớ đã tắt chế độ nhại giọng rồi nhé.")
    
    state.fakevoice_target = member.id
    await ctx.send(f"🦜 *Bật chế độ Fakevoice:* Bất cứ thứ gì **{member.display_name}** chat, tớ sẽ đọc lên trong Kênh thoại!")

@bot.command(name="tts")
async def tts_command(ctx, *, text: str):
    """Phát văn bản thành giọng nói Google"""
    if not ctx.author.voice: return await ctx.send("Cậu vào Kênh thoại trước nhé!")
    vc = ctx.voice_client or await ctx.author.voice.channel.connect()

    was_playing = vc.is_playing()
    if was_playing: vc.pause()

    async with ctx.typing():
        tts_file = f"gtts_{ctx.guild.id}_{int(time.time() * 1000)}.mp3"
        try:
            gTTS(text=text, lang='vi').save(tts_file)
            
            def after_speaking(error):
                if os.path.exists(tts_file): os.remove(tts_file)
                if was_playing and vc and vc.is_paused(): vc.resume()

            vc.play(discord.FFmpegPCMAudio(tts_file), after=after_speaking)
            await ctx.send(f"🗣️ *Yuri cất lời:* \"{text}\"")
        except Exception:
            if was_playing and vc.is_paused(): vc.resume()

@bot.command(name="autoplay", aliases=["ap"])
async def autoplay_cmd(ctx):
    """Bật/Tắt chế độ tự động phát nhạc"""
    state = get_state(ctx.guild.id)
    state.autoplay = not state.autoplay
    vc = ctx.voice_client
    if state.autoplay and vc and not vc.is_playing() and len(state.queue) == 0:
        bot.loop.create_task(play_next(ctx))
    await ctx.send(f"🎲 Chế độ AutoPlay đã được **{'BẬT' if state.autoplay else 'TẮT'}**.")

@bot.command(name="vol", aliases=["volume"])
async def set_volume(ctx, vol: int):
    """Chỉnh âm lượng bot (Mỗi nấc 25%)"""
    if vol not in [25, 50, 75, 100]: return await ctx.send("Chọn âm lượng: **25, 50, 75, hoặc 100** nhé.")
    state = get_state(ctx.guild.id)
    state.volume = vol / 100.0
    vc = ctx.voice_client
    if vc and vc.source and isinstance(vc.source, discord.PCMVolumeTransformer):
        vc.source.volume = state.volume
    await ctx.send(f"🔊 Âm lượng đang ở mức **{vol}%**.")

@bot.command(name="play", aliases=["p"])
async def play(ctx, *, query: str):
    """Phát nhạc SoundCloud"""
    if not ctx.author.voice: return await ctx.send("Cậu vào một Kênh thoại trước nhé!")
    vc = ctx.voice_client or await ctx.author.voice.channel.connect()

    state = get_state(ctx.guild.id)
    state.last_query = query
    async with ctx.typing():
        search_query = query if query.startswith("http") else f"scsearch:{query}"
        info = await asyncio.to_thread(lambda: ytdl.extract_info(search_query, download=False))
        if not info: return await ctx.send("Không tìm thấy bài hát...")

        entries = info['entries'] if 'entries' in info and query.startswith("http") else [info['entries'][0] if 'entries' in info else info]
        for entry in entries:
            if entry: state.queue.append({'title': entry.get('title'), 'url': entry.get('url'), 'webpage_url': entry.get('webpage_url', query), 'requester': ctx.author.display_name})

        if not vc.is_playing() and not vc.is_paused():
            await play_next(ctx)
        else:
            await ctx.send(f"🌸 Đã thêm **{len(entries)}** bài vào hàng đợi.")

@bot.command(name="oneshot")
async def oneshot(ctx, *, prompt: str):
    """Sáng tác một truyện ngắn trực tiếp trên khung chat"""
    async with ctx.typing():
        try:
            res = yuri_model.generate_content(f"Viết truyện ngắn oneshot sâu sắc về: '{prompt}'. Góc nhìn của Yuri.")
            await ctx.send(embed=discord.Embed(title="🖋️ Tác Phẩm Oneshot Của Yuri", description=res.text, color=discord.Color.purple()))
        except Exception: await ctx.send("Tâm trí tớ đang xao nhãng...")

@bot.command(name="doctieuthuyet")
async def doctieuthuyet(ctx, *, args: str):
    """!doctieuthuyet <Chủ đề> | <Link nhạc nền>"""
    if not ctx.author.voice: return await ctx.send("Cậu hãy vào kênh thoại nhé.")
    vc = ctx.voice_client or await ctx.author.voice.channel.connect()
    
    parts = args.split("|")
    story_prompt, bgm_link = parts[0].strip(), parts[1].strip() if len(parts) > 1 else None

    async with ctx.typing():
        res = yuri_model.generate_content(f"Viết 1 đoạn truyện 200 từ thật sâu sắc về: {story_prompt}")
        story_text = res.text
        await ctx.send(embed=discord.Embed(title="📖 Đang đọc tác phẩm", description=story_text, color=discord.Color.dark_purple()))

        tts_file = f"story_{ctx.guild.id}_{int(time.time()*1000)}.mp3"
        await edge_tts.Communicate(story_text, "vi-VN-HoaiMyNeural").save(tts_file)

        if vc.is_playing(): vc.stop()

        def cleanup_and_resume(error):
            if os.path.exists(tts_file): os.remove(tts_file)
            asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop)

        if bgm_link:
            info = await asyncio.to_thread(lambda: ytdl.extract_info(bgm_link, download=False))
            bgm_url = info['url'] if 'url' in info else info['entries'][0]['url']
            opts = {
                'before_options': f'-i "{tts_file}" -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
                'options': '-vn -filter_complex "[0:a]volume=1.0[tts];[1:a]volume=0.25[bgm];[tts][bgm]amix=inputs=2:duration=first"'
            }
            vc.play(discord.FFmpegPCMAudio(bgm_url, **opts), after=cleanup_and_resume)
        else:
            vc.play(discord.FFmpegPCMAudio(tts_file), after=cleanup_and_resume)

@bot.command(name="Yhelps")
async def yhelps(ctx):
    """Bảng hiển thị toàn bộ lệnh"""
    embed = discord.Embed(title="✨ Sổ Tay Lệnh Của Yuri", color=discord.Color.purple())
    embed.add_field(name="🎵 Nhạc", value="`!play <link>`: Bật nhạc\n`!autoplay`: Bật/Tắt AutoPlay\n`!vol <25/50/75/100>`: Chỉnh âm lượng", inline=False)
    embed.add_field(name="📖 Văn Học", value="`!oneshot <chủ đề>`: Yuri viết truyện ngắn tại chat\n`!doctieuthuyet <chủ đề> | <link nhạc>`: Đọc truyện & mix nhạc nền tự động", inline=False)
    embed.add_field(name="🗣️ Voice & AI", value="`!tts <chữ>`: Giọng Google Việt Nam\n`!fakevoice @User`: Nhại nội dung chat của ai đó thành TTS\nTag `@Yuri` để trò chuyện", inline=False)
    await ctx.send(embed=embed)

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
