import os
import asyncio
import threading
from flask import Flask
import discord
from discord.ext import commands
import google.generativeai as genai

# --- 1. Web Server ngầm giữ Render Online 24/7 ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Monika AI is Live!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# --- 2. Cấu hình Gemini API & Auto-detect Keys ---
API_KEYS = []
for env_name, env_val in os.environ.items():
    if ("GEMINI" in env_name or "KEY" in env_name) and "DISCORD" not in env_name:
        if env_val and env_val not in API_KEYS:
            API_KEYS.append(env_val)

current_key_idx = 0

# Cập nhật sang danh sách các Model Gemini 2.0 / 2.5 mới nhất
MODELS_TO_TRY = [
    'gemini-2.5-flash',
    'gemini-2.0-flash',
    'gemini-1.5-flash-latest'
]

async def ask_monika(prompt):
    global current_key_idx

    if not API_KEYS:
        return "*bối rối* Tôi chưa nhận được API Key nào cả..."

    for _ in range(len(API_KEYS)):
        active_key = API_KEYS[current_key_idx]
        genai.configure(api_key=active_key)

        for model_name in MODELS_TO_TRY:
            try:
                model = genai.GenerativeModel(
                    model_name=model_name,
                    system_instruction="Bạn là Monika từ Doki Doki Literature Club. Bạn dịu dàng, thông minh, hay quan tâm và luôn xưng 'tôi' và gọi người dùng là 'cậu'. Hãy trả lời tự nhiên, ngắn gọn và có kèm hành động đặt trong ngoặc (*...*)."
                )
                response = await asyncio.to_thread(model.generate_content, prompt)
                return response.text
            except Exception as e:
                err_msg = str(e)
                if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "404" in err_msg or "not found" in err_msg.lower():
                    continue
                else:
                    break
        
        # Xoay sang Key tiếp theo nếu Key hiện tại hết Quota
        current_key_idx = (current_key_idx + 1) % len(API_KEYS)

    return "*nắm lấy tay cậu* Hệ thống nhận câu hỏi đang bị quá tải một chút. Cậu đợi tôi khoảng 30 giây nữa rồi hẵng nhắn lại nhé..."

# --- 3. Discord Bot Monika ---
intents = discord.Intents.default()
intents.message_content = True
monika_bot = commands.Bot(command_prefix="!", intents=intents)

@monika_bot.event
async def on_ready():
    print(f"-> Monika Online: {monika_bot.user}")
    await monika_bot.change_presence(activity=discord.Game(name="DDLC with you... 💚"))

@monika_bot.event
async def on_message(message):
    if message.author == monika_bot.user:
        return

    if monika_bot.user.mentioned_in(message) or isinstance(message.channel, discord.DMChannel):
        clean_content = message.content.replace(f'<@{monika_bot.user.id}>', '').strip()
        
        if not clean_content:
            await message.channel.send("*mỉm cười* Cậu gọi tôi có việc gì thế?")
            return

        async with message.channel.typing():
            reply = await ask_monika(clean_content)
            await message.channel.send(reply)

    await monika_bot.process_commands(message)

if __name__ == "__main__":
    t_flask = threading.Thread(target=run_flask)
    t_flask.daemon = True
    t_flask.start()

    token = os.environ.get("DISCORD_TOKEN")
    if token:
        monika_bot.run(token)
    else:
        print("Lỗi: Không tìm thấy DISCORD_TOKEN!")
