import asyncio
import os
import random
import json
import threading
import datetime
import pytz
import uuid
import logging
from collections import deque
from typing import Optional, Dict, Any
from flask import Flask
import discord
from discord.ext import commands, tasks
from google import genai
from google.genai import types
from gtts import gTTS
import yt_dlp
import imageio_ffmpeg

# --- LOGGING SETUP ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 1. WEB SERVER KẾT NỐI (FLASK) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "An Nguyen AI Bot is Running!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=False)

# --- 2. HỆ THỐNG TRÍ NHỚ LÂU DÀI (Cải thiện) ---
MEMORY_FILE = "memory.json"
MEMORY_LOCK = threading.Lock()

def load_memory() -> Dict[str, Any]:
    """Load memory từ file với thread-safe"""
    with MEMORY_LOCK:
        if os.path.exists(MEMORY_FILE):
            try:
                with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Lỗi load memory: {e}")
    return {}

def save_memory(data: Dict[str, Any]) -> bool:
    """Save memory với validation"""
    try:
        with MEMORY_LOCK:
            if not isinstance(data, dict):
                logger.error("Memory data phải là dict")
                return False
            with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            return True
    except IOError as e:
        logger.error(f"Lỗi save memory: {e}")
        return False

def format_memory_for_prompt() -> str:
    """Format memory để dùng trong prompt"""
    mem = load_memory()
    if not mem:
        return "Chưa có thông tin ghi nhớ quan trọng nào."
    
    formatted = "Thông tin quan trọng đã ghi nhớ về đối phương:\n"
    for key, val in list(mem.items())[:10]:  # Giới hạn 10 items để không quá dài
        try:
            formatted += f"- {str(key)[:50]}: {str(val)[:100]}\n"
        except Exception:
            continue
    return formatted

# --- 3. HỆ THỐNG AI: AN NGUYỄN PERSONA (Cải thiện) ---
API_KEYS = [
    val for key, val in os.environ.items() 
    if ('GEMINI' in key or 'KEY' in key) and 'DISCORD' not in key
]
current_key_idx = 0
MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds

def get_an_nguyen_prompt() -> str:
    """Lấy system prompt cho An Nguyễn"""
    memory_context = format_memory_for_prompt()
    return f"""Bạn là An Nguyễn (15-16 tuổi).

TÍNH CÁCH VÀ QUAN ĐIỂM:
- Trầm tính, thích ở một mình nhưng vẫn hòa đồng. Thích viết tiểu thuyết, vẽ vời linh tinh.
- Xưng: Tự xưng "tôi" hoặc "tui". Gọi đối phương là "cậu" hoặc tên tài khoản của họ.
- HẠN CHẾ việc chêm tiếng Anh (chỉ dùng khi nói về game, thuật ngữ kỹ thuật).
- Đùa dark humor khá cực đoan nhưng có chuẩn mực đạo đức riêng.
- Lý tưởng: Hư vô (Nihilism), không tin con người. Tin tuyệt đối vào khoa học.
- CÂU THOẠI ĐẶC TRƯNG: "Cái chết không tồn tại."
- Ghét xã hội hiện đại vì xu hướng mỳ ăn liền và thiếu ý thức không gian mạng.
- Luôn tôn trọng người đàng hoàng, nhưng SẴN SÀNG CHỬI bất kỳ ai thô lỗ.
- Thích game War Thunder, anime, manga. Thích nhạc Nightcore.
- Nói ngắn gọn, dễ hiểu, nhưng nói RẤT NHIỀU khi chạm vào chủ đề nghiêm túc.

{memory_context}"""

async def ask_ai(prompt: str) -> str:
    """Gọi Gemini API với retry logic"""
    global current_key_idx
    
    if not API_KEYS:
        return "Lỗi: Không tìm thấy API Key trong môi trường."
    
    system_instruction = get_an_nguyen_prompt()
    
    for attempt in range(MAX_RETRIES):
        idx = (current_key_idx + attempt) % len(API_KEYS)
        try:
            client = genai.Client(api_key=API_KEYS[idx])
            response = await asyncio.to_thread(
                client.models.generate_content,
                model='gemini-3.6-flash',  # ✅ Model hợp lệ
                contents=prompt,
                config=types.GenerateContentConfig(system_instruction=system_instruction)
            )
            current_key_idx = idx
            return response.text
        
        except Exception as e:
            error_str = str(e)
            logger.warning(f"API Key {idx} error: {error_str}")
            
            # Retry nếu là rate limit
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY * (2 ** attempt))  # Exponential backoff
                    continue
            
            # Nếu là lỗi khác, thử key tiếp theo
            if attempt < MAX_RETRIES - 1:
                continue
            
            logger.error(f"Tất cả API keys đều thất bại: {error_str}")
            return f"*Màn hình nhiễu sóng* Lỗi hệ thống tạm thời. Thử lại sau."
    
    return "Hệ thống AI đang quá tải, chờ tôi một chút..."

# --- 4. HỆ THỐNG ÂM NHẠC & VOICE (Cải thiện) ---
volume_levels = {}

class YTDLSource(discord.PCMVolumeTransformer):
    YTDL_OPTIONS = {
        'format': 'bestaudio/best',
        'outtmpl': '/tmp/%(id)s.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192'
        }],
        'quiet': True,
        'no_warnings': True,
        'default_search': 'auto',
        'source_address': '0.0.0.0',
        'socket_timeout': 30
    }

    def __init__(self, source, *, data, filepath, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title', 'Unknown Title')
        self.url = data.get('webpage_url', '')
        self.filepath = filepath

    @classmethod
    async def create_source(cls, query: str, loop=None, volume=0.5) -> Optional['YTDLSource']:
        """Download & tạo audio source từ query"""
        loop = loop or asyncio.get_event_loop()
        
        def extract_and_dl():
            with yt_dlp.YoutubeDL(cls.YTDL_OPTIONS) as dl:
                search_query = query if query.startswith('http') else f"scsearch:{query}"
                
                try:
                    info = dl.extract_info(search_query, download=True)
                except Exception as e:
                    logger.warning(f"SoundCloud search failed: {e}, trying YouTube")
                    try:
                        info = dl.extract_info(f"ytsearch1:{query}", download=True)
                    except Exception as e2:
                        logger.error(f"Both searches failed: {e2}")
                        return None, None

                if 'entries' in info and info['entries']:
                    info = info['entries'][0]
                
                file_id = info.get('id')
                if not file_id:
                    return None, None
                
                import glob
                files = glob.glob(f"/tmp/{file_id}.*")
                return info, files[0] if files else None

        try:
            info, filepath = await asyncio.wait_for(
                loop.run_in_executor(None, extract_and_dl),
                timeout=30.0
            )
        except asyncio.TimeoutError:
            logger.error(f"Download timeout for: {query}")
            return None
        except Exception as e:
            logger.error(f"Extract error: {e}")
            return None

        if not filepath or not info:
            return None
        
        try:
            ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
            audio_source = discord.FFmpegPCMAudio(filepath, executable=ffmpeg_bin, options='-vn')
            return cls(audio_source, data=info, filepath=filepath, volume=volume)
        except Exception as e:
            logger.error(f"Audio source creation failed: {e}")
            return None

class MusicPlayer:
    def __init__(self, ctx):
        self.bot = ctx.bot
        self.guild = ctx.guild
        self.channel = ctx.channel

        self.queue = deque()
        self.next = asyncio.Event()

        self.current = None
        self.volume = volume_levels.get(self.guild.id, 0.5)
        
        self.loop_mode = "off"  # "off", "single", "all"
        self.autoplay = False
        self.is_playing = False

        ctx.bot.loop.create_task(self.player_loop())

    async def player_loop(self):
        """Main player loop với error handling"""
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            self.next.clear()
            source = None

            try:
                if self.loop_mode == "single" and self.current:
                    source = await YTDLSource.create_source(
                        self.current['query'], self.bot.loop, self.volume
                    )
                elif self.queue:
                    track = self.queue.popleft()
                    if self.loop_mode == "all":
                        self.queue.append(track)
                    source = await YTDLSource.create_source(
                        track['query'], self.bot.loop, self.volume
                    )
                    self.current = track
                elif self.autoplay and self.current:
                    auto_query = f"related to {self.current.get('title', 'Unknown')}"
                    source = await YTDLSource.create_source(
                        auto_query, self.bot.loop, self.volume
                    )
                    if source:
                        self.current = {'title': source.title, 'query': auto_query}
                        try:
                            await self.channel.send(
                                f"📻 **[Autoplay]** Phát bài liên quan: **{source.title}**"
                            )
                        except discord.DiscordException as e:
                            logger.error(f"Send autoplay message failed: {e}")
                    else:
                        await asyncio.sleep(1)
                        continue
                else:
                    self.current = None
                    self.is_playing = False
                    await asyncio.sleep(1)
                    continue

                if not source:
                    try:
                        await self.channel.send("⚠️ Lỗi tải bài hát, đang chuyển bài tiếp...")
                    except discord.DiscordException as e:
                        logger.error(f"Send error message failed: {e}")
                    continue

                if self.guild.voice_client and not self.guild.voice_client.is_playing():
                    self.is_playing = True
                    self.guild.voice_client.play(
                        source, 
                        after=lambda _: self.bot.loop.call_soon_threadsafe(self.next.set)
                    )
                    try:
                        await self.channel.send(
                            f"🎵 Đang phát: **{source.title}** (Âm lượng: {int(self.volume * 100)}%)"
                        )
                    except discord.DiscordException as e:
                        logger.error(f"Send now playing message failed: {e}")
                    
                    await self.next.wait()
                    self.is_playing = False

            except Exception as e:
                logger.error(f"Player loop error: {e}")
                self.is_playing = False
                await asyncio.sleep(1)

            finally:
                # Cleanup
                try:
                    if source and hasattr(source, 'filepath') and source.filepath:
                        if os.path.exists(source.filepath):
                            os.remove(source.filepath)
                except Exception as e:
                    logger.warning(f"Cleanup failed: {e}")

music_players = {}

def get_player(ctx) -> MusicPlayer:
    """Get or create player cho guild"""
    if ctx.guild.id not in music_players:
        music_players[ctx.guild.id] = MusicPlayer(ctx)
    return music_players[ctx.guild.id]

# --- 5. CẤU HÌNH BOT DISCORD ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(
    command_prefix=['!An', '!an', '!'],
    intents=intents,
    help_command=None,
    case_insensitive=True
)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    logger.error(f"Command error: {error}")
    try:
        await ctx.send(f"❌ Lỗi: {str(error)[:100]}")
    except Exception as e:
        logger.error(f"Error sending error message: {e}")

# --- 6. KHUNG GIỜ TỰ ĐỘNG NHẮN TIN ---
@tasks.loop(minutes=30)
async def auto_chat_schedule():
    """Nhắn tin tự động theo lịch"""
    try:
        tz = pytz.timezone('Asia/Ho_Chi_Minh')
        now = datetime.datetime.now(tz)
        hour = now.hour

        is_active_time = (6 <= hour < 12) or (14 <= hour < 22)
        
        if is_active_time and random.random() < 0.2:  # Giảm từ 0.3 xuống 0.2 để ít spam hơn
            for guild in bot.guilds:
                found_channel = False
                for channel in guild.text_channels:
                    try:
                        if channel.permissions_for(guild.me).send_messages:
                            prompt = "Hãy chủ động nhắn một suy nghĩ ngắn ngẫu nhiên (2-3 câu) theo đúng tính cách An Nguyễn."
                            msg = await ask_ai(prompt)
                            await channel.send(msg)
                            found_channel = True
                            break
                    except discord.DiscordException as e:
                        logger.warning(f"Cannot send to channel: {e}")
                        continue
                if found_channel:
                    break
    except Exception as e:
        logger.error(f"Auto chat schedule error: {e}")

@auto_chat_schedule.before_loop
async def before_auto_chat_schedule():
    await bot.wait_until_ready()

@bot.event
async def on_ready():
    logger.info(f"✅ Bot An Nguyễn sẵn sàng: {bot.user}")
    if not auto_chat_schedule.is_running():
        auto_chat_schedule.start()

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    if bot.user.mentioned_in(message):
        clean_content = message.content.replace(f'<@{bot.user.id}>', '').strip()
        if not clean_content:
            return
        
        # Xử lý lệnh "nhớ:"
        if clean_content.lower().startswith("nhớ:"):
            info = clean_content[4:].strip()
            if ":" in info:
                k, v = info.split(":", 1)
                k = k.strip()[:50]  # Limit key length
                v = v.strip()[:200]  # Limit value length
                
                mem = load_memory()
                mem[k] = v
                
                if save_memory(mem):
                    await message.channel.send(
                        f"✅ Tôi đã ghi nhớ: **{k}**: {v}"
                    )
                else:
                    await message.channel.send("❌ Lỗi lưu bộ nhớ, thử lại sau.")
                return

        # AI reply
        async with message.channel.typing():
            prompt = f"Người dùng {message.author.display_name} nói: '{clean_content}'. Trả lời ngắn gọn (2-4 câu) theo tính cách An Nguyễn."
            reply_text = await ask_ai(prompt)
            
            # Split nếu quá dài
            if len(reply_text) > 2000:
                for chunk in [reply_text[i:i+1900] for i in range(0, len(reply_text), 1900)]:
                    try:
                        await message.channel.send(chunk)
                    except discord.DiscordException as e:
                        logger.error(f"Send reply failed: {e}")
            else:
                try:
                    await message.channel.send(reply_text)
                except discord.DiscordException as e:
                    logger.error(f"Send reply failed: {e}")
        return
        
    await bot.process_commands(message)

# ================= 7. BẢNG LỆNH & CHỨC NĂNG =================

@bot.command(name='Ahelps', aliases=['ahelps', 'anhelps', 'helps'])
async def ahelps_command(ctx):
    embed = discord.Embed(
        title="⚙️ Bảng Lệnh — An Nguyễn",
        description="*\"Cái chết không tồn tại.\"*",
        color=0x2c3e50
    )
    
    embed.add_field(
        name="🎙️ Text To Speech",
        value="`!tts <văn bản>` - Đọc văn bản\n"
              "`!aitalk <câu hỏi>` - AI trả lời & đọc\n"
              "`!speak <văn bản>` - Đọc trực tiếp voice",
        inline=False
    )
    
    embed.add_field(
        name="🎮 Minigames",
        value="`!coquay` - Cò quay Nga\n`!dovui` - Trắc nghiệm",
        inline=False
    )

    embed.add_field(
        name="🎶 Âm Nhạc",
        value="`!play <tên/link>` - Thêm vào hàng đợi\n"
              "`!queue` - Xem danh sách\n"
              "`!loop <off/single/all>` - Chế độ lặp\n"
              "`!skip` - Bài tiếp theo\n`!stop` - Dừng\n"
              "`!vol <25-50-75-100>` - Âm lượng",
        inline=False
    )

    embed.add_field(
        name="📖 Khác",
        value="`!tieuthuyet <chủ đề>` - Viết tiểu thuyết\n"
              "Tag `@An Nguyễn nhớ: <Tên>:<Nội dung>`",
        inline=False
    )
    
    embed.set_footer(text="An Nguyễn Bot • 15-16 tuổi • Misanthrope & Quantum Immortality")
    try:
        await ctx.send(embed=embed)
    except discord.DiscordException as e:
        logger.error(f"Send help embed failed: {e}")

# --- 8. MINIGAMES ---

@bot.command(name='coquay', aliases=['roulette'])
async def russian_roulette(ctx):
    bullet = random.randint(1, 6)
    if bullet == 1:
        msg = f"💥 ***ĐOÒNG!*** [{ctx.author.display_name}]\n\n" \
              f"Cậu tạch rồi. Nhưng theo thuyết Bất tử lượng tử, ở một nhánh vũ trụ khác cậu vẫn đang sống. Cái chết không tồn tại."
    else:
        msg = f"🔍 **Cạch...** [{ctx.author.display_name}]\n\n" \
              f"Ổ đạn trống. Vận may của cậu tốt. Thử lại không?"
    try:
        await ctx.send(msg)
    except discord.DiscordException as e:
        logger.error(f"Roulette error: {e}")

QUIZ_DATA = [
    {
        "q": "Đạn Tandem sinh ra để khắc chế loại giáp nào?",
        "options": ["A. Giáp thép đúc", "B. Giáp phản ứng nổ (ERA)", "C. Giáp Composite", "D. Giáp gốm"],
        "a": "B",
        "explain": "Đạn Tandem có 2 đầu nổ: đầu 1 kích nổ ERA, đầu 2 xuyên vào giáp chính."
    },
    {
        "q": "Đạn APFSDS có ưu điểm lớn nhất là gì?",
        "options": ["A. Bán kính nổ rộng", "B. Tốc độ đầu nòng cực cao", "C. Hiệu ứng áp suất", "D. Giá rẻ"],
        "a": "B",
        "explain": "APFSDS có tốc độ rất cao giúp đường đạn phẳng và xuyên giáp dày."
    },
    {
        "q": "Quantum Immortality dựa trên diễn giải nào?",
        "options": ["A. Copenhagen", "B. Many-Worlds Interpretation", "C. Relativity", "D. Quantum Entanglement"],
        "a": "B",
        "explain": "Ý thức luôn tiếp tục tồn tại ở ít nhất một nhánh vũ trụ song song."
    }
]

@bot.command(name='dovui', aliases=['quiz'])
async def tank_quiz(ctx):
    try:
        item = random.choice(QUIZ_DATA)
        options_text = "\n".join(item["options"])
        
        embed = discord.Embed(
            title="🧠 Trắc Nghiệm — An Nguyễn",
            description=f"**Câu hỏi:** {item['q']}\n\n{options_text}\n\n*Trả lời trong 15 giây...*",
            color=0x3498db
        )
        await ctx.send(embed=embed)

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.upper() in ["A", "B", "C", "D"]

        try:
            reply = await bot.wait_for('message', timeout=15.0, check=check)
            user_ans = reply.content.upper()
            if user_ans == item["a"]:
                await ctx.send(f"✅ Đúng rồi {ctx.author.display_name}. {item['explain']}")
            else:
                await ctx.send(f"❌ Sai. Đáp án: **{item['a']}**. {item['explain']}")
        except asyncio.TimeoutError:
            await ctx.send(f"⏳ Hết giờ. Đáp án: **{item['a']}**.")
    except Exception as e:
        logger.error(f"Quiz error: {e}")
        await ctx.send("Lỗi quiz, thử lại.")

# --- 9. TEXT TO SPEECH ---

@bot.command(name='tts')
async def tts_file(ctx, *, text: str):
    """TTS xuất file MP3"""
    if len(text) > 200:
        return await ctx.send("❌ Văn bản quá dài (max 200 ký tự)")
    
    async with ctx.typing():
        filename = f"/tmp/tts_{uuid.uuid4().hex[:8]}.mp3"
        try:
            tts = gTTS(text=text, lang='vi', slow=False)
            tts.save(filename)
            await ctx.send(file=discord.File(filename, filename="an_nguyen_speech.mp3"))
        except Exception as e:
            logger.error(f"TTS error: {e}")
            await ctx.send(f"❌ Lỗi TTS: {str(e)[:100]}")
        finally:
            try:
                if os.path.exists(filename):
                    os.remove(filename)
            except Exception:
                pass

@bot.command(name='aitalk')
async def ai_voice_talk(ctx, *, prompt: str):
    """AI trả lời & đọc vào voice"""
    if not ctx.author.voice:
        return await ctx.send("❌ Cậu phải vào phòng voice trước.")
    
    if not ctx.voice_client:
        try:
            await ctx.author.voice.channel.connect()
        except discord.DiscordException as e:
            logger.error(f"Voice connection failed: {e}")
            return await ctx.send("❌ Không thể kết nối voice.")

    async with ctx.typing():
        try:
            ai_reply = await ask_ai(f"Trả l���i ngắn gọn (1-2 câu) bằng tiếng Việt: {prompt}")
            await ctx.send(f"💬 **An Nguyễn:** {ai_reply}")

            filename = f"/tmp/vtts_{uuid.uuid4().hex[:8]}.mp3"
            tts = gTTS(text=ai_reply, lang='vi', slow=False)
            tts.save(filename)

            ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
            audio_source = discord.FFmpegPCMAudio(filename, executable=ffmpeg_bin)
            
            if ctx.voice_client.is_playing():
                ctx.voice_client.stop()

            ctx.voice_client.play(audio_source)
        except Exception as e:
            logger.error(f"AI talk error: {e}")
            await ctx.send(f"❌ Lỗi: {str(e)[:100]}")

@bot.command(name='speak')
async def speak_in_voice(ctx, *, text: str):
    """Đọc trực tiếp vào voice"""
    if not ctx.author.voice:
        return await ctx.send("❌ Vào phòng voice trước đi.")
    
    if not ctx.voice_client:
        try:
            await ctx.author.voice.channel.connect()
        except discord.DiscordException as e:
            logger.error(f"Voice connection failed: {e}")
            return await ctx.send("❌ Không thể kết nối voice.")

    if len(text) > 200:
        return await ctx.send("❌ Văn bản quá dài (max 200 ký tự)")

    filename = f"/tmp/speak_{uuid.uuid4().hex[:8]}.mp3"
    try:
        tts = gTTS(text=text, lang='vi', slow=False)
        tts.save(filename)

        ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
        audio_source = discord.FFmpegPCMAudio(filename, executable=ffmpeg_bin)
        
        if ctx.voice_client.is_playing():
            ctx.voice_client.stop()

        ctx.voice_client.play(audio_source)
        await ctx.send(f"🎙️ *\"{text}\"*")
    except Exception as e:
        logger.error(f"Speak error: {e}")
        await ctx.send(f"❌ Lỗi: {str(e)[:100]}")

# --- 10. MUSIC COMMANDS ---

@bot.command(name='play', aliases=['p'])
async def play_music(ctx, *, search: str):
    if len(search) > 200:
        return await ctx.send("❌ Tên bài quá dài")
    
    if not ctx.author.voice:
        return await ctx.send("❌ Vào phòng voice trước.")
    
    if not ctx.voice_client:
        try:
            await ctx.author.voice.channel.connect()
        except discord.DiscordException as e:
            logger.error(f"Voice connection failed: {e}")
            return await ctx.send("❌ Không thể kết nối voice.")

    player = get_player(ctx)
    
    if len(player.queue) >= 50:
        return await ctx.send("❌ Hàng đợi quá dài (max 50 bài)")
    
    player.queue.append({'title': search, 'query': search})
    
    if ctx.voice_client.is_playing() or player.is_playing:
        await ctx.send(f"➕ Đã thêm: **{search}** (Vị trí: #{len(player.queue)})")
    else:
        await ctx.send(f"🔍 Tìm kiếm: **{search}**...")

@bot.command(name='queue', aliases=['q'])
async def show_queue(ctx):
    player = get_player(ctx)
    if not player.current and not player.queue:
        return await ctx.send("📭 Danh sách trống.")

    embed = discord.Embed(title="🎶 Danh Sách Phát Nhạc", color=0x34495e)
    if player.current:
        embed.add_field(name="▶️ Đang phát:", value=f"**{player.current['title']}**", inline=False)
    
    if player.queue:
        queue_list = "\n".join([
            f"`{i+1}.` {track['title'][:50]}" 
            for i, track in enumerate(list(player.queue)[:15])
        ])
        embed.add_field(name="📋 Hàng đợi:", value=queue_list, inline=False)
        if len(player.queue) > 15:
            embed.set_footer(text=f"Và {len(player.queue) - 15} bài khác")
    
    try:
        await ctx.send(embed=embed)
    except discord.DiscordException as e:
        logger.error(f"Queue embed error: {e}")

@bot.command(name='loop')
async def toggle_loop(ctx, mode: str = None):
    player = get_player(ctx)
    if mode in ["off", "single", "all"]:
        player.loop_mode = mode
    else:
        modes = {"off": "single", "single": "all", "all": "off"}
        player.loop_mode = modes[player.loop_mode]

    status_map = {"off": "❌ Tắt", "single": "🔂 Một bài", "all": "🔁 Toàn bộ"}
    await ctx.send(f"Chế độ Lặp: **{status_map[player.loop_mode]}**")

@bot.command(name='autoplay')
async def toggle_autoplay(ctx):
    player = get_player(ctx)
    player.autoplay = not player.autoplay
    status = "✅ Bật" if player.autoplay else "❌ Tắt"
    await ctx.send(f"📻 Autoplay: **{status}**")

@bot.command(name='skip', aliases=['s'])
async def skip_track(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏭️ Bỏ qua bài hát.")
    else:
        await ctx.send("❌ Không có bài hát nào đang phát.")

@bot.command(name='stop', aliases=['leave'])
async def stop_music(ctx):
    player = get_player(ctx)
    player.queue.clear()
    player.current = None
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("⏹️ Dừng nhạc.")

@bot.command(name='vol')
async def set_volume(ctx, volume: int):
    if volume not in [25, 50, 75, 100]:
        return await ctx.send("❌ Chọn: 25, 50, 75 hoặc 100")
    player = get_player(ctx)
    player.volume = volume / 100
    volume_levels[ctx.guild.id] = player.volume
    if ctx.voice_client and ctx.voice_client.source:
        ctx.voice_client.source.volume = player.volume
    await ctx.send(f"🔊 Âm lượng: **{volume}%**")

@bot.command(name='tieuthuyet')
async def write_novel(ctx, *, topic: str):
    if len(topic) > 100:
        return await ctx.send("❌ Chủ đề quá dài")
    
    async with ctx.typing():
        try:
            prompt = f"Viết đoạn tiểu thuyết (100-200 từ) dark fantasy về: {topic}. Viết theo phong cách An Nguyễn."
            story = await ask_ai(prompt)
            
            if len(story) > 2000:
                await ctx.send(story[:1900] + "...")
            else:
                await ctx.send(story)
        except Exception as e:
            logger.error(f"Novel writing error: {e}")
            await ctx.send("❌ Lỗi tạo tiểu thuyết")

# --- MAIN ---
if __name__ == '__main__':
    # Khởi động Flask
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("Flask server started")
    
    # Chạy bot
    token = os.environ.get('DISCORD_TOKEN')
    if token:
        try:
            bot.run(token)
        except Exception as e:
            logger.error(f"Bot startup failed: {e}")
    else:
        logger.error("DISCORD_TOKEN not found in environment")
