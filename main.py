import asyncio
import os
import random
import threading
import discord
from discord.ext import commands
from flask import Flask
from google import genai
from google.genai import types

# ================= 1. CẤU HÌNH WEB SERVER (FLASK) =================
app = Flask(__name__)


@app.route("/")
def home():
  return "War Thunder Complete Unified Yuri Bot is operational..."


def run_flask():
  port = int(os.environ.get("PORT", 8080))
  app.run(host="0.0.0.0", port=port)


def keep_alive():
  server_thread = threading.Thread(target=run_flask)
  server_thread.daemon = True
  server_thread.start()


# ================= 2. CẤU HÌNH BOT & GEMINI (YURI) =================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "YOUR_DISCORD_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY")

ai_client = genai.Client(api_key=GEMINI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

game_sessions = {}

TEAM_TANKS = {
    "Nga": ["t-80", "t-90a", "bmp-3", "bmpt", "t-90m", "t-72b3m", "t-64bv"],
    "Uka": ["m1a1-abrams", "leopard-2a7", "bradley-tusk", "puma", "bmp-2", "t-72b3"],
}

# Yuri: Sĩ quan tham mưu sắc sảo, ngắn gọn, phảng phất nét nội tâm sắc lạnh phong cách DDLC
YURI_MILITARY_SYSTEM_PROMPT = (
    "Bạn là Yuri - Sĩ quan tham mưu kiêm pháo thủ thiết giáp, mang phong cách "
    "sắc sảo, trầm lặng và phảng phất nét nội tâm sắc bén, tinh tế đặc trưng của "
    "nhân vật Yuri trong DDLC nhưng đặt trong bối cảnh quân sự hiện đại. "
    "Bạn nói cực kỳ ngắn gọn (dưới 3 câu), sắc lạnh, thỉnh thoảng có chút biểu cảm "
    "cực đoan hoặc ám ảnh nhẹ về chiến thuật và vũ khí. "
    "Chỉ nói dài hơn một chút khi tương tác trực tiếp trong giao diện FCS để phân tích thông số kỹ thuật."
)

WEATHER_CONDITIONS = [
    {"name": "☀️ Ban ngày quang đãng", "requires_rest": False},
    {"name": "🌧️ Bão tố sấm sét", "requires_rest": True},
    {"name": "🌙 Trời tối mịt mờ", "requires_rest": True},
    {"name": "🌫️ Sương mù dày đặc", "requires_rest": False},
]


# ================= 3. GIAO DIỆN FCS KÈM THỜI TIẾT & CHU KỲ =================
def generate_fcs_view(
    tank_name,
    fcs_type="t72",
    speed="Đứng yên",
    ammo="APFSDS",
    hp=100,
    mission="Tiêu diệt địch",
    enemy_info="",
    cooldown_turns=0,
    locked_distance=1650,
    weather="☀️ Ban ngày quang đãng",
    action_counter=0,
):
  hp_bar = "█" * (hp // 20) + "░" * (5 - (hp // 20))

  screen = f"""[BATTLEFIELD] Thời tiết: {weather} | Chu kỳ hành động: {action_counter}/4
[FCS: {tank_name.upper()} - {fcs_type.upper()}] | HP: [{hp_bar}] {hp}%
⚙️ Cơ động: {speed} | 📦 Đạn: {ammo}
🎯 Mục tiêu: {mission}"""

  if hp <= 0:
    screen += "\n❌ CHIẾN TRƯỜNG KẾT THÚC: Xe tăng đã bị tiêu diệt hoàn toàn!"
  elif cooldown_turns > 0:
    screen += f"\n⚠️ TRẠNG THÁI: Sửa chữa dã chiến (Còn {cooldown_turns} lượt)"
  elif "Bão tố" in weather or "Trời tối" in weather:
    screen += "\n⚠️ CẢNH BÁO: Thời tiết khắc nghiệt! Bắt buộc phải dùng [Nghỉ ngơi] hoặc lệnh !Ysleep."

  if enemy_info and hp > 0:
    screen += f"\n-----------------------------------\n{enemy_info}"
  elif hp > 0:
    screen += (
        "\n-----------------------------------\n   [ LOCKED: Cự ly"
        f" {locked_distance}m ]\n   /   [ + ]   \\"
    )

  return screen


class QuickChatFCSView(discord.ui.View):

  def __init__(self, ctx, tank_name):
    super().__init__(timeout=180)
    self.ctx = ctx
    self.tank_name = tank_name
    self.fcs_type = (
        "basic"
        if any(x in tank_name.lower() for x in ["bmp-2", "bradley", "puma"])
        else "t72"
    )
    self.speed = "Đứng yên ngắm bắn"
    self.ammo = "APFSDS"
    self.hp = 100
    self.missions = [
        "Tiêu diệt kẻ địch",
        "Chiếm cứ khu vực",
        "Trinh sát chiến tuyến",
        "Tiên phong đột phá",
    ]
    self.current_mission = random.choice(self.missions)
    self.enemy_status_text = ""
    self.repair_cooldown = 0
    self.locked_distance = random.randint(800, 2400)
    self.current_weather = random.choice(WEATHER_CONDITIONS)
    self.action_counter = 0

  def check_weather_cycle(self):
    self.action_counter += 1
    if self.action_counter >= 4:
      self.action_counter = 0
      if "Bão tố" in self.current_weather["name"] or "Trời tối" in self.current_weather["name"]:
        if random.randint(1, 100) <= 75:
          self.current_weather = {"name": "☀️ Ban ngày quang đãng", "requires_rest": False}
          return True
    return False

  async def execute_action(
      self, interaction: discord.Interaction, action_type, action_desc
  ):
    if interaction.user != self.ctx.author:
      return await interaction.response.send_message(
          "⚠️ Không có quyền can thiệp!", ephemeral=True
      )
    if self.hp <= 0:
      return await interaction.response.send_message(
          "❌ Chiến trường đã kết thúc! Xe tăng của bạn đã bị bắn hạ.",
          ephemeral=True,
      )

    is_severe_weather = self.current_weather["requires_rest"]
    if is_severe_weather and action_type not in ["rest", "binocular"]:
      return await interaction.response.send_message(
          f"⚠️ Thời tiết đang là **{self.current_weather['name']}**! Bạn bắt"
          " buộc phải dùng nút **[🏕️ Nghỉ ngơi]** hoặc lệnh `!Ysleep` để trú ẩn.",
          ephemeral=True,
      )

    if self.repair_cooldown > 0 and action_type != "status_check":
      if action_type in ["repair", "rest"]:
        return await interaction.response.send_message(
            "⚠️ Xe tăng đang trong quá trình bảo dưỡng/sửa chữa rồi!",
            ephemeral=True,
        )

      self.repair_cooldown -= 1
      await interaction.response.defer()

      temp_msg = await interaction.followup.send(
          "⏳ *Yuri lúng túng ôm bảng mạch: 'Vui lòng đợi một lát...'*"
      )
      await asyncio.sleep(1.0)
      try:
        await temp_msg.delete()
      except Exception:
        pass

      extra_info = (
          f"🛠️ Đang sửa chữa dã chiến... (Còn lại {self.repair_cooldown} lượt)."
      )
      result_title = "⚙️ BẢO TRÌ CHIẾN TRƯỜNG"

      hit_taken = random.randint(15, 45)
      self.hp = max(0, self.hp - hit_taken)
      extra_info += f"\n⚠️ **Địch chớp thời cơ nã pháo:** Gây -{hit_taken}% HP!"

      if self.hp <= 0:
        self.current_mission = "Đã bị bắn hạ (Wrecked)"
        result_title = "❌ CHIẾN TRƯỜNG KẾT THÚC"

      weather_cleared = self.check_weather_cycle()
      if weather_cleared:
        extra_info += "\n⛅ **Bầu trời chuyển biến:** Bão tố/Đêm tối đã chấm dứt!"

      screen_art = generate_fcs_view(
          self.tank_name,
          self.fcs_type,
          self.speed,
          self.ammo,
          self.hp,
          self.current_mission,
          self.enemy_status_text,
          self.repair_cooldown,
          self.locked_distance,
          self.current_weather["name"],
          self.action_counter,
      )
      embed = discord.Embed(
          title=result_title,
          description=f"*Yuri mồ hôi đầm đìa: 'Cố lên, xe chịu đựng chút nữa!'*\n\n```text\n{screen_art}\n
