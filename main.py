import os
import asyncio
import collections
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

# Cấu hình AI Gemini
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

# Cấu hình Discord Bot
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# Cấu hình YT-DLP dành riêng cho SoundCloud
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
    'default_search': 'scsearch',  # Mặc định tìm kiếm trên SoundCloud
    'source_address': '0.0.0.0'
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

# Quản lý trạng thái phát nhạc cho từng Server (Guild)
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

# --- SỰ KIỆN KHỞI ĐỘNG ---
@bot.event
async def on_ready():
    print(f"=== Bot Yuri đã đăng nhập thành công: {bot.user} ===")
    await bot.change_presence(activity=discord.Game(name="!help | Đọc tiểu thuyết cùng Yuri"))

# --- TRÒ CHUYỆN CÙNG YURI (AI CHAT) ---
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Nếu bot được nhắc tên (mention) hoặc trả lời tin nhắn của bot
    if bot.user.mentioned_in(message) and not message.mention_everyone:
        clean_content = message.content.replace(f'<@{bot.user.id}>', '').strip()
        if clean_content:
            async with message.channel.typing():
                try:
                    response = yuri_model.generate_content(clean_content)
                    await message.reply(response.text)
                except Exception as e:
                    await message.reply("Ưm... Tớ xin lỗi, đầu óc tớ hơi mơ hồ một chút. Cậu có thể nói lại được không?")
                    print(f"Gemini Error: {e}")
            return

    await bot.process_commands(message)

# --- HỆ THỐNG PHÁT NHẠC SOUNDCLOUD ---

async def play_next(ctx):
    state = get_music_state(ctx.guild.id)
    vc = ctx.voice_client

    if not vc or not vc.is_connected():
        return

    # Xử lý chế độ Lặp lại (Loop)
    if state.loop_mode == "track" and state.current_track:
        state.queue.appendleft(state.current_track)
    elif state.loop_mode == "queue" and state.current_track:
        state.queue.append(state.current_track)

    # Xử lý AutoPlay khi hàng đợi trống
    if len(state.queue) == 0 and state.autoplay and state.last_query:
        try:
            search_term = f"scsearch5:{state.last_query} radio"
            info = await asyncio.to_thread(lambda: ytdl.extract_info(search_term, download=False))
            if 'entries' in info and len(info['entries']) > 1:
                next_entry = info['entries'][1] # Lấy bài liên quan
                track = {
                    'title': next_entry.get('title', 'Unknow Track'),
                    'url': next_entry.get('url'),
                    'webpage_url': next_entry.get('webpage_url'),
                    'requester': 'Yuri AutoPlay'
                }
                state.queue.append(track)
        except Exception as e:
            print(f"AutoPlay error: {e}")

    if len(state.queue) == 0:
        state.current_track = None
        await ctx.send("*Hàng đợi nhạc đã hết. Tớ xin phép giữ yên lặng một lúc nhé...*")
        return

    track = state.queue.popleft()
    state.current_track = track

    try:
        source = discord.FFmpegPCMAudio(track['url'], **FFMPEG_OPTIONS)
        vc.play(source, after=lambda e: bot.loop.create_task(play_next(ctx)))
        
        embed = discord.Embed(
            title="🎶 Đang phát nhạc từ SoundCloud",
            description=f"**[{track['title']}]({track['webpage_url']})**",
            color=discord.Color.purple()
        )
        embed.set_footer(text=f"Yêu cầu bởi: {track['requester']} | Loop: {state.loop_mode} | AutoPlay: {'Bật' if state.autoplay else 'Tắt'}")
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(f"Đã xảy ra lỗi khi phát nhạc: {e}")
        bot.loop.create_task(play_next(ctx))

@bot.command(name="play", aliases=["p"])
async def play(ctx, *, query: str):
    """Phát nhạc từ SoundCloud (Nhập tên bài hát hoặc URL SoundCloud)"""
    if not ctx.author.voice:
        return await ctx.send("Cậu cần vào một Kênh thoại (Voice Channel) trước đã nhé!")

    vc = ctx.voice_client
    if not vc:
        vc = await ctx.author.voice.channel.connect()

    state = get_music_state(ctx.guild.id)
    state.last_query = query

    async with ctx.typing():
        # Tìm kiếm hoặc lấy thông tin từ SoundCloud
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
            await ctx.send(f"🌸 Đã thêm vào hàng đợi: **{track['title']}**")

@bot.command(name="skip", aliases=["s"])
async def skip(ctx):
    """Bỏ qua bài hát hiện tại"""
    vc = ctx.voice_client
    if vc and vc.is_playing():
        vc.stop()
        await ctx.send("*Đã bỏ qua bài hát theo ý cậu.*")
    else:
        await ctx.send("Hiện tại đâu có bài hát nào đang phát đâu cậu?")

@bot.command(name="loop")
async def loop(ctx, mode: str = None):
    """Cài đặt chế độ lặp lại: !loop off | !loop track | !loop queue"""
    state = get_music_state(ctx.guild.id)
    valid_modes = ["off", "track", "queue"]

    if not mode or mode.lower() not in valid_modes:
        return await ctx.send(f"Chế độ hiện tại: `{state.loop_mode}`. Cú pháp đúng: `!loop off` / `!loop track` / `!loop queue`")

    state.loop_mode = mode.lower()
    await ctx.send(f"🔮 Đã chuyển chế độ lặp lại thành: **{state.loop_mode}**")

@bot.command(name="autoplay")
async def autoplay(ctx):
    """Bật/tắt chế độ tự động phát bài hát tương tự trên SoundCloud"""
    state = get_music_state(ctx.guild.id)
    state.autoplay = not state.autoplay
    status = "Bật" if state.autoplay else "Tắt"
    await ctx.send(f"🎧 Chế độ AutoPlay SoundCloud hiện đã: **{status}**")

@bot.command(name="queue", aliases=["q"])
async def queue(ctx):
    """Xem danh sách hàng đợi nhạc"""
    state = get_music_state(ctx.guild.id)
    if not state.queue and not state.current_track:
        return await ctx.send("Hàng đợi hiện đang trống.")

    msg = f"**Bài đang phát:** {state.current_track['title'] if state.current_track else 'Không có'}\n\n**Hàng đợi:**\n"
    for idx, t in enumerate(state.queue, 1):
        msg += f"{idx}. {t['title']} (Yêu cầu bởi: {t['requester']})\n"

    await ctx.send(msg[:2000])

@bot.command(name="stop", aliases=["leave"])
async def stop(ctx):
    """Dừng nhạc và ngắt kết nối voice"""
    vc = ctx.voice_client
    if vc:
        state = get_music_state(ctx.guild.id)
        state.queue.clear()
        state.current_track = None
        await vc.disconnect()
        await ctx.send("*Tớ tạm biệt nhé, chúc cậu một ngày bình yên.*")

# --- TÍNH NĂNG ĐỌC & SÁNG TÁC TIỂU THUYẾT ---

@bot.command(name="doctieuthuyet", aliases=["novel", "story"])
async def doctieuthuyet(ctx, *, description: str):
    """
    Tạo tiểu thuyết ngắn theo mô tả và phát giọng đọc trực tiếp vào Voice Channel.
    Cú pháp: !doctieuthuyet <mô tả cốt truyện>
    """
    async with ctx.typing():
        # 1. Tạo tiểu thuyết bằng AI Gemini theo phong cách Yuri
        prompt = (
            f"Hãy viết một truyện ngắn/chương tiểu thuyết ngắn khoảng 200-300 từ dựa trên mô tả sau: '{description}'. "
            f"Yêu cầu: Văn phong sâu sắc, giàu hình ảnh tâm lý, có chất nghệ thuật tinh tế của Yuri. "
            f"Không kèm lời thoại ngoài lề, chỉ tập trung vào văn bản tiểu thuyết."
        )
        try:
            story_res = yuri_model.generate_content(prompt)
            story_text = story_res.text
        except Exception as e:
            return await ctx.send(f"Tớ không thể tập trung sáng tác câu chuyện lúc này... Lỗi: {e}")

        # Send đoạn truyện chữ vào Text Channel
        embed = discord.Embed(
            title="📖 Tác Phẩm Mới Của Yuri",
            description=story_text,
            color=discord.Color.dark_purple()
        )
        embed.set_footer(text=f"Sáng tác theo ý tưởng của: {ctx.author.display_name}")
        await ctx.send(embed=embed)

        # 2. Chuyển văn bản thành giọng đọc truyền cảm bằng Edge-TTS (Tiếng Việt)
        tts_file = f"story_{ctx.guild.id}.mp3"
        voice = "vi-VN-HoaiMyNeural"  # Giọng nữ truyền cảm
        communicate = edge_tts.Communicate(story_text, voice)
        await communicate.save(tts_file)

        # 3. Kết nối Voice Channel và đọc truyện
        if not ctx.author.voice:
            return await ctx.send("*Tớ đã viết xong câu chuyện trên. Nếu cậu muốn tớ đọc cho nghe, hãy vào Kênh thoại nhé!*")

        vc = ctx.voice_client
        if not vc:
            vc = await ctx.author.voice.channel.connect()

        # Dừng nhạc nếu đang phát để đọc truyện
        if vc.is_playing():
            vc.stop()

        def after_reading(error):
            if os.path.exists(tts_file):
                os.remove(tts_file)

        source = discord.FFmpegPCMAudio(tts_file)
        vc.play(source, after=after_reading)
        await ctx.send("🎙️ *Yuri bắt đầu cất giọng đọc câu chuyện cho cậu nghe...*")

# --- LỆNH TRỢ GIÚP ---
@bot.command(name="help")
async def help_command(ctx):
    embed = discord.Embed(
        title="📚 Sổ Tay Hướng Dẫn - Bot Yuri",
        description="Chào cậu, tớ là Yuri. Dưới đây là những điều tớ có thể làm giúp cậu:",
        color=discord.Color.purple()
    )
    embed.add_field(
        name="💬 AI Trò chuyện",
        value="• Tag `@Yuri` + lời nhắn để trò chuyện trực tiếp với tớ.",
        inline=False
    )
    embed.add_field(
        name="🎶 Phát Nhạc SoundCloud",
        value=(
            "• `!play <tên bài/link>`: Tìm & phát nhạc trên SoundCloud.\n"
            "• `!skip`: Bỏ qua bài hiện tại.\n"
            "• `!loop <off|track|queue>`: Chế độ lặp lại.\n"
            "• `!autoplay`: Tự động tìm phát bài liên quan khi hết nhạc.\n"
            "• `!queue`: Xem danh sách chờ.\n"
            "• `!stop`: Tắt nhạc & rời kênh thoại."
        ),
        inline=False
    )
    embed.add_field(
        name="📖 Tiểu Thuyết & Giọng Đọc",
        value="• `!doctieuthuyet <mô tả>`: Tớ sẽ sáng tác truyện theo ý cậu và cất giọng đọc trong Voice Channel.",
        inline=False
    )
    await ctx.send(embed=embed)

# Khởi chạy Bot
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("Lỗi: Chưa cấu hình DISCORD_TOKEN trong file .env")
    else:
        bot.run(DISCORD_TOKEN)
