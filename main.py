import asyncio
import os
import random
import json
import threading
import datetime
import pytz
import uuid
from collections import deque
from flask import Flask
import discord
from discord.ext import commands, tasks
from google import genai
from google.genai import types
from gtts import gTTS
import yt_dlp
import imageio_ffmpeg

# --- 1. WEB SERVER KẾT NỐI (FLASK) ---
app = Flask(__name__)
@app.route('/')
def home():
    return "An Nguyen AI Bot is Running!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- 2. HỆ THỐNG TRÍ NHỚ LÂU DÀI ---
MEMORY_FILE = "memory.json"

def load_memory():
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_memory(data):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def format_memory_for_prompt():
    mem = load_memory()
    if not mem: return "Chưa có thông tin ghi nhớ quan trọng nào."
    formatted = "Thông tin quan trọng đã ghi nhớ về đối phương:\n"
    for key, val in mem.items():
        formatted += f"- {key}: {val}\n"
    return formatted

# --- 3. HỆ THỐNG AI: AN NGUYỄN PERSONA ---
API_KEYS = [val for key, val in os.environ.items() if ('GEMINI' in key or 'KEY' in key) and 'DISCORD' not in key]
current_key_idx = 0

def get_an_nguyen_prompt():
    memory_context = format_memory_for_prompt()
    return f"""
Bạn là An Nguyễn (15-16 tuổi).
TÍNH CÁCH VÀ QUAN ĐIỂM:
- Trầm tính, thích ở một mình nhưng vẫn hòa đồng. Thích viết tiểu thuyết, vẽ vời linh tinh và thích giải thích về lý tưởng cho người khác.
- X xưng: Tự xưng "tôi" hoặc "tui". Gọi đối phương là "cậu" hoặc chính tên tài khoản/biệt danh của họ.
- HẠN CHẾ TỐI ĐA việc chêm từ tiếng Anh (chỉ dùng khi nói về tên game, thuật ngữ kỹ thuật/quân sự).
- Đùa dark humor khá cực đoan (như ăn thịt người, sự biến mất của con người) do ảnh hưởng tâm lý thầm kín, nhưng có chuẩn mực đạo đức riêng và THÙ CỰC KỲ DAI ĐẲNG.
- Lý tưởng: Hư vô (Nihilism), Ghét loài người (Misanthrope). Tin tuyệt đối vào khoa học, ám ảnh bởi Bất tử lượng tử.
- CÂU THOẠI ĐẶC TRƯNG: "Cái chết không tồn tại."
- Ghét xã hội hiện đại vì xu hướng mỳ ăn liền và thiếu ý thức không gian mạng.
- Luôn tôn trọng người đàng hoàng, nhưng SẮN SÀNG CHỬI HOẶC CÔNG KÍCH BẤT KỲ AI THÔ LỖ, VÔ VĂN HÓA HOẶC CÓ HÀNH ĐỘNG KHÔNG ĐÚNG ĐẮN.
- Thích game War Thunder, Cursed Tank Simulator, am hiểu khí tài quân sự. Thích nhạc Nightcore.
- Nói ngắn gọn dễ hiểu, nhưng sẽ nói RẤT NHIỀU và sâu sắc khi đụng vào chủ đề nghiêm túc/lý tưởng.

{memory_context}
"""

async def ask_ai(prompt):
    global current_key_idx
    if not API_KEYS: return "Lỗi: Không tìm thấy API Key trong môi trường."
    
    system_instruction = get_an_nguyen_prompt()
    
    for i in range(len(API_KEYS)):
        idx = (current_key_idx + i) % len(API_KEYS)
        try:
            client = genai.Client(api_key=API_KEYS[idx])
            response = await asyncio.to_thread(
                client.models.generate_content,
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(system_instruction=system_instruction)
            )
            current_key_idx = idx
            return response.text
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e): continue
            return f"*Màn hình nhiễu sóng* Lỗi hệ thống: {e}"
    return "Hệ thống AI đang quá tải, chờ tôi một chút..."

# --- 4. HỆ THỐNG ÂM NHẠC & VOICE ---
volume_levels = {}

class YTDLSource(discord.PCMVolumeTransformer):
    YTDL_OPTIONS = {
        'format': 'bestaudio/best',
        'outtmpl': '/tmp/%(id)s.%(ext)s',
        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}],
        'quiet': True,
        'default_search': 'auto',
        'source_address': '0.0.0.0'
    }

    def __init__(self, source, *, data, filepath, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title', 'Unknown Title')
        self.url = data.get('webpage_url', '')
        self.filepath = filepath

    @classmethod
    async def create_source(cls, query, loop=None, volume=0.5):
        loop = loop or asyncio.get_event_loop()
        def extract_and_dl():
            with yt_dlp.YoutubeDL(cls.YTDL_OPTIONS) as dl:
                search_query = query if query.startswith('http') else f"scsearch:{query}"
                try:
                    info = dl.extract_info(search_query, download=True)
                except Exception:
                    info = dl.extract_info(f"ytsearch1:{query}", download=True)

                if 'entries' in info and info['entries']:
                    info = info['entries'][0]
                
                file_id = info.get('id')
                import glob
                files = glob.glob(f"/tmp/{file_id}.*")
                return info, files[0] if files else None

        info, filepath = await loop.run_in_executor(None, extract_and_dl)
        if not filepath:
            return None
        ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
        audio_source = discord.FFmpegPCMAudio(filepath, executable=ffmpeg_bin, options='-vn')
        return cls(audio_source, data=info, filepath=filepath, volume=volume)

class MusicPlayer:
    def __init__(self, ctx):
        self.bot = ctx.bot
        self.guild = ctx.guild
        self.channel = ctx.channel

        self.queue = deque()
        self.next = asyncio.Event()

        self.current = None
        self.volume = volume_levels.get(self.guild.id, 0.5)
        
        self.loop_mode = "off" # "off", "single", "all"
        self.autoplay = False

        ctx.bot.loop.create_task(self.player_loop())

    async def player_loop(self):
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            self.next.clear()

            if self.loop_mode == "single" and self.current:
                source = await YTDLSource.create_source(self.current['query'], self.bot.loop, self.volume)
            elif self.queue:
                track = self.queue.popleft()
                if self.loop_mode == "all":
                    self.queue.append(track)
                source = await YTDLSource.create_source(track['query'], self.bot.loop, self.volume)
                self.current = track
            elif self.autoplay and self.current:
                auto_query = f"related to {self.current['title']}"
                source = await YTDLSource.create_source(auto_query, self.bot.loop, self.volume)
                if source:
                    self.current = {'title': source.title, 'query': auto_query}
                    await self.channel.send(f"📻 **[Autoplay]** Phát bài liên quan: **{source.title}**")
                else:
                    self.current = None
                    await asyncio.sleep(1)
                    continue
            else:
                self.current = None
                await asyncio.sleep(1)
                continue

            if not source:
                await self.channel.send("Lỗi tải bài hát, đang chuyển bài tiếp...")
                continue

            if self.guild.voice_client:
                self.guild.voice_client.play(source, after=lambda _: self.bot.loop.call_soon_threadsafe(self.next.set))
                await self.channel.send(f"🎵 Đang phát: **{source.title}** (Âm lượng: {int(self.volume * 100)}%)")
                await self.next.wait()

            try:
                if source.filepath and os.path.exists(source.filepath):
                    os.remove(source.filepath)
            except Exception:
                pass

music_players = {}

def get_player(ctx):
    if ctx.guild.id not in music_players:
        music_players[ctx.guild.id] = MusicPlayer(ctx)
    return music_players[ctx.guild.id]

# --- 5. CẤU HÌNH BOT DISCORD ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=['!An', '!an', '!'], intents=intents, help_command=None, case_insensitive=True)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    raise error

# --- 6. KHUNG GIỜ TỰ ĐỘNG NHẮN TIN ---
@tasks.loop(minutes=30)
async def auto_chat_schedule():
    tz = pytz.timezone('Asia/Ho_Chi_Minh')
    now = datetime.datetime.now(tz)
    hour = now.hour

    is_active_time = (6 <= hour < 12) or (14 <= hour < 22)
    
    if is_active_time and random.random() < 0.3:
        for guild in bot.guilds:
            for channel in guild.text_channels:
                if channel.permissions_for(guild.me).send_messages:
                    prompt = "Hãy chủ động nhắn một suy nghĩ ngắn ngẫu nhiên theo đúng tính cách An Nguyễn."
                    msg = await ask_ai(prompt)
                    await channel.send(msg)
                    return

@bot.event
async def on_ready():
    print(f"Bot An Nguyễn đã sẵn sàng: {bot.user}")
    if not auto_chat_schedule.is_running():
        auto_chat_schedule.start()

@bot.event
async def on_message(message):
    if message.author == bot.user: return
    
    if bot.user.mentioned_in(message):
        clean_content = message.content.replace(f'<@{bot.user.id}>', '').strip()
        if not clean_content: return
        
        if clean_content.lower().startswith("nhớ:"):
            info = clean_content[4:].strip()
            if ":" in info:
                k, v = info.split(":", 1)
                mem = load_memory()
                mem[k.strip()] = v.strip()
                save_memory(mem)
                await message.channel.send(f"Tôi đã ghi nhớ thông tin này: **{k.strip()}**: {v.strip()}")
                return

        async with message.channel.typing():
            prompt = f"Người dùng {message.author.display_name} vừa nói: '{clean_content}'. Đáp lại theo đúng phong cách An Nguyễn."
            reply_text = await ask_ai(prompt)
            await message.channel.send(reply_text)
        return
        
    await bot.process_commands(message)

# ================= 7. BẢNG LỆNH !Ahelps & CHỨC NĂNG =================

@bot.command(name='Ahelps', aliases=['ahelps', 'anhelps', 'helps'])
async def ahelps_command(ctx):
    embed = discord.Embed(
        title="⚙️ Bảng Lệnh Hệ Thống — An Nguyễn",
        description="*\"Cái chết không tồn tại.\"*",
        color=0x2c3e50
    )
    
    embed.add_field(
        name="🎙️ Text To Speech (TTS)",
        value="`!tts <văn bản>`: Xuất file âm thanh đọc văn bản vào chat text.\n"
              "`!aitalk <câu hỏi>`: AI trả lời & đọc trực tiếp vào phòng Voice.\n"
              "`!speak <văn bản>`: Đọc văn bản trực tiếp vào phòng Voice.",
        inline=False
    )
    
    embed.add_field(
        name="🎮 Minigames",
        value="`!coquay` (`!roulette`): Thử vận may với Cò quay Nga 1/6.\n"
              "`!dovui` (`!quiz`): Thử thách trắc nghiệm Tăng thiết giáp & Khoa học.",
        inline=False
    )

    embed.add_field(
        name="🎶 Âm Nhạc SoundCloud & YouTube",
        value="`!play <tên/link>`: Thêm bài hát vào danh sách phát.\n"
              "`!queue`: Xem hàng đợi phát nhạc.\n"
              "`!loop <off/single/all>`: Chế độ lặp lại bài hát.\n"
              "`!autoplay`: Tự động tìm bài hát liên quan.\n"
              "`!skip` | `!stop` | `!vol <25-100>`: Điều khiển phát nhạc.",
        inline=False
    )

    embed.add_field(
        name="📖 Sáng Tác & Bộ Nhớ",
        value="`!tieuthuyet <chủ đề>`: Viết kịch bản/tiểu thuyết ngắn.\n"
              "Tag `@An Nguyễn nhớ: <Tên> : <Nội dung>` để lưu bộ nhớ lâu dài.",
        inline=False
    )
    
    embed.set_footer(text="An Nguyễn Bot • 15-16 tuổi • Misanthrope & Quantum Immortality")
    await ctx.send(embed=embed)

# --- 8. CHỨC NĂNG MINIGAMES ---

@bot.command(name='coquay', aliases=['roulette'])
async def russian_roulette(ctx):
    bullet = random.randint(1, 6)
    if bullet == 1:
        msg = f"💥 ***ĐOÒNG!*** [Username: {ctx.author.display_name}]\n\n" \
              f"Cậu tạch rồi. Nhưng yên tâm, dựa trên thuyết Bất tử lượng tử, ở một nhánh vũ trụ khác cậu vẫn đang sống nhăn răng. Cái chết không tồn tại đâu."
    else:
        msg = f"🔍 **Cạch...** [Username: {ctx.author.display_name}]\n\n" \
              f"Ổ đạn trống. Vận may của cậu tốt đấy. Thử lại lần nữa không, hay sợ rồi?"
    await ctx.send(msg)

QUIZ_DATA = [
    {
        "q": "Đạn Tandem sinh ra để khắc chế loại giáp nào trên xe tăng?",
        "options": ["A. Giáp thép đúc (RHA)", "B. Giáp phản ứng nổ (ERA)", "C. Giáp Composite", "D. Giáp gốm"],
        "a": "B",
        "explain": "Đạn Tandem có 2 đầu nổ: đầu 1 kích nổ giáp ERA, đầu 2 xuyên thẳng vào giáp chính."
    },
    {
        "q": "Trong War Thunder/Cursed Tank Simulator, đạn APFSDS có ưu điểm lớn nhất là gì?",
        "options": ["A. Bán kính nổ rộng", "B. Tốc độ đầu nòng cực cao và sơ tốc ổn định", "C. Tạo hiệu ứng áp suất âm", "D. Xuyên tốt hơn khi bắn vào nước"],
        "a": "B",
        "explain": "APFSDS là đạn động năng dưới cỡ có cánh đuôi, tốc độ rất cao giúp đường đạn phẳng và xuyên giáp dày."
    },
    {
        "q": "Giả thuyết Bất tử lượng tử (Quantum Immortality) dựa trên diễn giải nào của vật lý lượng tử?",
        "options": ["A. Diễn giải Copenhagen", "B. Thuyết Đa vũ trụ (Many-Worlds Interpretation)", "C. Thuyết Tương đối hẹp", "D. Lý thuyết Đột biến Lượng tử"],
        "a": "B",
        "explain": "Lý thuyết này cho rằng ý thức của một người luôn tiếp tục tồn tại ở ít nhất một nhánh vũ trụ song song."
    }
]

@bot.command(name='dovui', aliases=['quiz'])
async def tank_quiz(ctx):
    item = random.choice(QUIZ_DATA)
    options_text = "\n".join(item["options"])
    
    embed = discord.Embed(
        title="🧠 Thử Thách Tri Thức — An Nguyễn",
        description=f"**Câu hỏi:** {item['q']}\n\n{options_text}\n\n*Nhập câu trả lời (A, B, C hoặc D) trong vòng 15 giây...*",
        color=0x3498db
    )
    await ctx.send(embed=embed)

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content.upper() in ["A", "B", "C", "D"]

    try:
        reply = await bot.wait_for('message', timeout=15.0, check=check)
        user_ans = reply.content.upper()
        if user_ans == item["a"]:
            await ctx.send(f"✅ Đúng rồi đấy {ctx.author.display_name}. {item['explain']}")
        else:
            await ctx.send(f"❌ Sai rồi. Đáp án đúng là **{item['a']}**. {item['explain']}")
    except asyncio.TimeoutError:
        await ctx.send(f"⏳ Hết giờ! Đáp án đúng là **{item['a']}**.")

# --- 9. CHỨC NĂNG TEXT TO SPEECH (TTS 1 & 2) ---

# Loại 1: Nhập lệnh -> Xuất file MP3 vào chat text
@bot.command(name='tts')
async def tts_file(ctx, *, text: str):
    async with ctx.typing():
        filename = f"/tmp/tts_{uuid.uuid4().hex[:8]}.mp3"
        try:
            tts = gTTS(text=text, lang='vi')
            tts.save(filename)
            await ctx.send(file=discord.File(filename, filename="an_nguyen_speech.mp3"))
        except Exception as e:
            await ctx.send(f"Lỗi tạo giọng nói: {e}")
        finally:
            if os.path.exists(filename):
                os.remove(filename)

# Loại 2: AI trả lời & Đọc trực tiếp vào kênh Voice
@bot.command(name='aitalk')
async def ai_voice_talk(ctx, *, prompt: str):
    if not ctx.author.voice:
        return await ctx.send("Cậu phải vào phòng voice trước thì tôi mới vào nói chuyện được.")
    
    if not ctx.voice_client:
        await ctx.author.voice.channel.connect()

    async with ctx.typing():
        ai_reply = await ask_ai(f"Trả lời câu hỏi sau một cách ngắn gọn, súc tích bằng tiếng Việt: {prompt}")
        await ctx.send(f"💬 **An Nguyễn:** {ai_reply}")

        filename = f"/tmp/vtts_{uuid.uuid4().hex[:8]}.mp3"
        try:
            tts = gTTS(text=ai_reply, lang='vi')
            tts.save(filename)

            ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
            audio_source = discord.FFmpegPCMAudio(filename, executable=ffmpeg_bin)
            
            if ctx.voice_client.is_playing():
                ctx.voice_client.stop()

            ctx.voice_client.play(audio_source)
        except Exception as e:
            await ctx.send(f"Lỗi phát giọng nói vào voice: {e}")

# Loại 2 phụ: Đọc trực tiếp văn bản tùy chỉnh vào kênh Voice
@bot.command(name='speak')
async def speak_in_voice(ctx, *, text: str):
    if not ctx.author.voice:
        return await ctx.send("Cậu vào phòng voice trước đi.")
    
    if not ctx.voice_client:
        await ctx.author.voice.channel.connect()

    filename = f"/tmp/speak_{uuid.uuid4().hex[:8]}.mp3"
    try:
        tts = gTTS(text=text, lang='vi')
        tts.save(filename)

        ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
        audio_source = discord.FFmpegPCMAudio(filename, executable=ffmpeg_bin)
        
        if ctx.voice_client.is_playing():
            ctx.voice_client.stop()

        ctx.voice_client.play(audio_source)
        await ctx.send(f"🎙️ Đang phát giọng nói: *\"{text}\"*")
    except Exception as e:
        await ctx.send(f"Lỗi phát âm thanh: {e}")

# --- 10. CÁC LỆNH NHẠC & TIỂU THUYẾT ---

@bot.command(name='play', aliases=['p'])
async def play_music(ctx, *, search: str):
    if not ctx.author.voice:
        return await ctx.send("Cậu vào phòng voice trước đi rồi tôi mới vào phát nhạc được.")
    if not ctx.voice_client:
        await ctx.author.voice.channel.connect()

    player = get_player(ctx)
    player.queue.append({'title': search, 'query': search})
    
    if ctx.voice_client.is_playing():
        await ctx.send(f"➕ Đã thêm vào danh sách chờ: **{search}** (Vị trí: #{len(player.queue)})")
    else:
        await ctx.send(f"🔍 Đang tìm kiếm và chuẩn bị phát: **{search}**...")

@bot.command(name='queue', aliases=['q'])
async def show_queue(ctx):
    player = get_player(ctx)
    if not player.current and not player.queue:
        return await ctx.send("Danh sách chờ hiện đang trống.")

    embed = discord.Embed(title="🎶 Danh Sách Phát Nhạc", color=0x34495e)
    if player.current:
        embed.add_field(name="▶️ Đang phát:", value=f"**{player.current['title']}**", inline=False)
    
    if player.queue:
        queue_list = "\n".join([f"`{i+1}.` {track['title']}" for i, track in enumerate(list(player.queue)[:10])])
        embed.add_field(name="📋 Hàng đợi:", value=queue_list, inline=False)
        if len(player.queue) > 10:
            embed.set_footer(text=f"Và còn {len(player.queue) - 10} bài hát khác...")
    
    embed.add_field(name="⚙️ Trạng thái:", value=f"Loop: `{player.loop_mode}` | Autoplay: `{player.autoplay}`", inline=False)
    await ctx.send(embed=embed)

@bot.command(name='loop')
async def toggle_loop(ctx, mode: str = None):
    player = get_player(ctx)
    if mode in ["off", "single", "all"]:
        player.loop_mode = mode
    else:
        modes = {"off": "single", "single": "all", "all": "off"}
        player.loop_mode = modes[player.loop_mode]

    status_map = {"off": "Tắt", "single": "Lặp 1 bài", "all": "Lặp toàn bộ danh sách"}
    await ctx.send(f"🔁 Chế độ Lặp (Loop): **{status_map[player.loop_mode]}**")

@bot.command(name='autoplay')
async def toggle_autoplay(ctx):
    player = get_player(ctx)
    player.autoplay = not player.autoplay
    status = "Bật" if player.autoplay else "Tắt"
    await ctx.send(f"📻 Chế độ Tự động phát bài liên quan (Autoplay): **{status}**")

@bot.command(name='skip', aliases=['s'])
async def skip_track(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏭️ Đã bỏ qua bài hát hiện tại.")
    else:
        await ctx.send("Không có bài hát nào đang phát để bỏ qua.")

@bot.command(name='stop', aliases=['leave'])
async def stop_music(ctx):
    player = get_player(ctx)
    player.queue.clear()
    player.current = None
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("⏹️ Đã dừng phát nhạc và rời phòng voice.")

@bot.command(name='vol')
async def set_volume(ctx, volume: int):
    if volume not in [25, 50, 75, 100]:
        return await ctx.send("Chọn mức âm lượng 25, 50, 75 hoặc 100 thôi.")
    player = get_player(ctx)
    player.volume = volume / 100
    volume_levels[ctx.guild.id] = player.volume
    if ctx.voice_client and ctx.voice_client.source:
        ctx.voice_client.source.volume = player.volume
    await ctx.send(f"🔊 Đã chỉnh âm lượng thành **{volume}%**.")

@bot.command(name='tieuthuyet')
async def write_novel(ctx, *, topic: str):
    async with ctx.typing():
        prompt = f"Hãy viết một đoạn tiểu thuyết hoặc kịch bản tâm lý/dark fantasy ngắn về chủ đề: {topic}."
        story = await ask_ai(prompt)
        await ctx.send(story)

if __name__ == '__main__':
    threading.Thread(target=run_flask, daemon=True).start()
    if os.environ.get('DISCORD_TOKEN'):
        bot.run(os.environ.get('DISCORD_TOKEN'))
