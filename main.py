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
  return "War Thunder Complete Uncut Yuri Bot (APS/IRCM/ERA/Crew System) is operational..."

def run_flask():
  port = int(os.environ.get("PORT", 8080))
  app.run(host="0.0.0.0", port=port)

def keep_alive():
  server_thread = threading.Thread(target=run_flask)
  server_thread.daemon = True
  server_thread.start()

# ================= 2. CẤU HÌNH BOT & GEMINI (YURI) =================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

ai_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

game_sessions = {}
active_guesses = {}

TEAM_TANKS = {
    "Nga": ["t-80", "t-90a", "bmp-3", "bmpt", "t-90m", "t-72b3m", "t-64bv"],
    "Uka": ["m1a1-abrams", "leopard-2a7", "bradley-tusk", "puma", "bmp-2", "t-72b3"],
}

# Danh sách cấu hình trang bị kỹ thuật
LASER_RF_TANKS = ["t-90m", "t-90a", "t-72b3m", "t-80", "leopard-2a7", "m1a1-abrams", "puma", "bmpt"]
ATGM_TANKS = ["t-80", "t-90a", "t-90m", "t-72b3m", "bmp-2", "bmp-3", "bradley-tusk", "t-64bv"]
AUTOCANNON_TANKS = ["bmp-2", "bmp-3", "bradley-tusk", "puma", "bmpt"]

# Danh sách trang bị phòng thủ đặc chủng
APS_TANKS = ["t-90m"]
IRCM_TANKS = ["puma", "t-90a", "t-90m"]
ERA_TANKS = ["t-80", "t-90a", "t-90m", "t-72b3m", "t-72b3", "t-64bv", "bradley-tusk"]

YURI_MILITARY_SYSTEM_PROMPT = (
    "Bạn là Yuri - Sĩ quan tham mưu kiêm pháo thủ thiết giáp, mang phong cách "
    "sắc sảo, trầm lặng và phảng phất nét nội tâm sắc bén, tinh tế đặc trưng của "
    "nhân vật Yuri trong DDLC nhưng đặt trong bối cảnh quân sự hiện đại War Thunder. "
    "Bạn nói cực kỳ ngắn gọn (dưới 3 câu), sắc lạnh, thỉnh thoảng có chút biểu cảm "
    "cực đoan hoặc ám ảnh nhẹ về chiến thuật, dao găm và phân tích góc bắn thiết giáp. "
    "Chỉ nói dài hơn một chút khi tương tác trực tiếp trong giao diện FCS để phân tích thông số kỹ thuật."
)

WEATHER_CONDITIONS = [
    {"name": "☀️ Ban ngày quang đãng", "requires_rest": False},
    {"name": "🌧️ Bão tố sấm sét", "requires_rest": True},
    {"name": "🌙 Trời tối mịt mờ", "requires_rest": True},
    {"name": "🌫️ Sương mù dày đặc", "requires_rest": False},
]

# ================= 3. HÀM HIỂN THỊ HỆ THỐNG FCS =================
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
    aim_zeroing=1650,
    weather="☀️ Ban ngày quang đãng",
    action_counter=0,
    crew_status=None,
    has_lrf=False,
    defenses_info=""
):
  hp_bar = "█" * (hp // 20) + "░" * (5 - (hp // 20))

  if crew_status is None:
    crew_status = {"commander": True, "gunner": True, "driver": True, "loader": True}

  c_str = "🟢 Sẵn sàng" if crew_status["commander"] else "❌ HY SINH"
  g_str = "🟢 Sẵn sàng" if crew_status["gunner"] else "❌ HY SINH"
  d_str = "🟢 Sẵn sàng" if crew_status["driver"] else "❌ HY SINH"
  l_str = "🟢 Sẵn sàng" if crew_status["loader"] else "❌ HY SINH"

  lrf_str = " (LRF: TỰ ĐỘNG KHÓA)" if has_lrf else " (THỦ CÔNG)"

  screen = f"""[BATTLEFIELD] Thời tiết: {weather} | Chu kỳ hành động: {action_counter}/4
[FCS: {tank_name.upper()} - {fcs_type.upper()}] | HP: [{hp_bar}] {hp}%
⚙️ Cơ động: {speed} | 📦 Đạn: {ammo}
🛡️ Hệ thống phòng thủ: {defenses_info}
👨‍✈️ Kíp lái: [Trưởng xe: {c_str} | Pháo thủ: {g_str} | Lái xe: {d_str} | Nạp đạn: {l_str}]
🎯 Cự ly mục tiêu: {locked_distance}m | 📐 Thước ngắm: {aim_zeroing}m{lrf_str}
🎯 Nhiệm vụ: {mission}"""

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

# ================= 4. GIAO DIỆN NÚT BẤM INTERACTIVE (FCS VIEW) =================
class QuickChatFCSView(discord.ui.View):

  def __init__(self, ctx, tank_name):
    super().__init__(timeout=300)
    self.ctx = ctx
    self.tank_name = tank_name.lower()
    self.fcs_type = (
        "basic"
        if any(x in self.tank_name for x in ["bmp-2", "bradley", "puma"])
        else "t72"
    )
    self.speed = "Đứng yên ngắm bắn"
    self.ammo = "APFSDS" if self.tank_name not in AUTOCANNON_TANKS else "APDS Autocannon"
    self.hp = 100
    self.enemy_tank = random.choice(["t-90m", "t-90a", "m1a1-abrams", "leopard-2a7", "bradley-tusk", "puma"])
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
    self.aim_zeroing = 1000
    self.current_weather = random.choice(WEATHER_CONDITIONS)
    self.action_counter = 0

    # Cấu hình tính năng vũ khí & phòng thủ
    self.has_lrf = any(x in self.tank_name for x in LASER_RF_TANKS)
    self.has_atgm = any(x in self.tank_name for x in ATGM_TANKS)
    self.is_autocannon = any(x in self.tank_name for x in AUTOCANNON_TANKS)
    self.has_aps = any(x in self.tank_name for x in APS_TANKS)
    self.has_ircm = any(x in self.tank_name for x in IRCM_TANKS)
    self.has_era = any(x in self.tank_name for x in ERA_TANKS)

    # Trạng thái kíp lái
    self.crew = {"commander": True, "gunner": True, "driver": True, "loader": True}

    if not self.has_atgm:
      self.remove_item(self.btn_atgm)

  def get_defense_string(self, tank_n):
    defs = []
    if any(x in tank_n for x in APS_TANKS): defs.append("APS (25%)")
    if any(x in tank_n for x in IRCM_TANKS): defs.append("IRCM (35%)")
    if any(x in tank_n for x in ERA_TANKS): defs.append("ERA (55%)")
    return " | ".join(defs) if defs else "Giáp thép tiêu chuẩn"

  def check_weather_cycle(self):
    self.action_counter += 1
    if self.action_counter >= 4:
      self.action_counter = 0
      if "Bão tố" in self.current_weather["name"] or "Trời tối" in self.current_weather["name"]:
        if random.randint(1, 100) <= 75:
          self.current_weather = {"name": "☀️ Ban ngày quang đãng", "requires_rest": False}
          return True
    return False

  def apply_random_crew_casualty(self):
    alive_crew = [k for k, v in self.crew.items() if v]
    if alive_crew and random.randint(1, 100) <= 40:
      casualty = random.choice(alive_crew)
      self.crew[casualty] = False
      names = {"commander": "Trưởng xe", "gunner": "Pháo thủ", "driver": "Lái xe", "loader": "Pháo thủ nạp đạn"}
      return f"\n⚠️ **THIỆT HẠI KÍP LÁI:** {names[casualty]} đã hy sinh!"
    return ""

  async def execute_action(
      self, interaction: discord.Interaction, action_type, action_desc
  ):
    if interaction.user != self.ctx.author:
      return await interaction.response.send_message(
          "⚠️ Không có quyền can thiệp vào bảng điều khiển này!", ephemeral=True
      )
    if self.hp <= 0:
      return await interaction.response.send_message(
          "❌ Chiến trường đã kết thúc! Xe tăng của bạn đã bị tiêu diệt hoàn toàn.",
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
            "⚠️ Xe tăng đang trong quá trình bảo dưỡng/sửa chữa dã chiến!",
            ephemeral=True,
        )

      self.repair_cooldown -= 1
      await interaction.response.defer()

      temp_msg = await interaction.followup.send(
          "⏳ *Yuri lúng túng ôm bảng mạch: 'Vui lòng đợi một lát, hệ thống đang tự động khôi phục...'*"
      )
      await asyncio.sleep(1.0)
      try:
        await temp_msg.delete()
      except Exception:
        pass

      extra_info = f"🛠️ Đang sửa chữa dã chiến... (Còn lại {self.repair_cooldown} lượt)."
      result_title = "⚙️ BẢO TRÌ CHIẾN TRƯỜNG"

      hit_taken = random.randint(15, 45)
      self.hp = max(0, self.hp - hit_taken)
      extra_info += f"\n\n⚠️ **KẺ ĐỊCH PHẢN CÔNG: Gây ra {hit_taken}% sát thương!**"
      extra_info += self.apply_random_crew_casualty()

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
          self.aim_zeroing,
          self.current_weather["name"],
          self.action_counter,
          self.crew,
          self.has_lrf,
          self.get_defense_string(self.tank_name)
      )

      embed = discord.Embed(
          title=result_title,
          description=f"> 🗡️ *\"Yuri mồ hôi đầm đìa: 'Cố lên, xe đang chịu đựng thêm đòn đánh!'\"*\n\n```text\n{screen_art}\n```",
          color=discord.Color.red() if self.hp <= 0 else discord.Color.orange(),
      )
      embed.add_field(name="🛡️ Khí tài", value=f"`{self.tank_name.upper()}`", inline=True)
      embed.add_field(name="❤️ HP Hiện tại", value=f"**{self.hp}%**", inline=True)
      embed.add_field(name="🌦️ Thời tiết", value=self.current_weather["name"], inline=True)

      if self.hp <= 0:
        embed.add_field(name="⚠️ Trạng thái", value="❌ **Đã bị tiêu diệt hoàn toàn!**", inline=False)
        self.clear_items()

      return await interaction.message.edit(embed=embed, view=self)

    await interaction.response.defer()
    temp_msg = await interaction.followup.send(
        "⏳ *Yuri vội vàng chỉnh lại gọng kính: 'Đang xử lý thông số tác chiến...'*"
    )

    async def delete_temp_msg():
      await asyncio.sleep(3)
      try:
        await temp_msg.delete()
      except Exception:
        pass

    asyncio.create_task(delete_temp_msg())

    extra_info = ""
    result_title = ""
    enemy_dmg = 0

    # 1. HỆ THỐNG NGHỈ NGƠI & THAY THẾ/HỒI PHỤC KÍP LÁI
    if action_type == "rest":
      ambush_chance = 45
      hit_by_enemy_first = random.randint(1, 100) <= ambush_chance
      if hit_by_enemy_first:
        enemy_surprise_dmg = random.randint(15, 35)
        self.hp = max(0, self.hp - enemy_surprise_dmg)
        extra_info = f"⚠️ **KẺ ĐỊCH PHỤC KÍCH KHÔNG KÍCH:** Gây ra {enemy_surprise_dmg}% sát thương!"
      else:
        extra_info = "🛡️ Cắm trại an toàn dã chiến. Yuri pha trà nóng động viên!"

      heal_amount = random.randint(25, 45)
      self.hp = min(100, self.hp + heal_amount)
      
      # THAY THẾ TOÀN BỘ KÍP LÁI HY SINH
      replaced_crew = [k for k, v in self.crew.items() if not v]
      self.crew = {"commander": True, "gunner": True, "driver": True, "loader": True}
      
      if replaced_crew:
        extra_info += "\n👨‍✈️ **BỔ SUNG LỰC LƯỢNG:** Đã thay thế và chữa trị toàn bộ thành viên kíp lái hy sinh!"
      
      extra_info += f"\n🏕️ Nghỉ ngơi thành công: Hồi phục **+{heal_amount}% HP**!"
      result_title = "🏕️ NGHỈ NGƠI & BỔ SUNG KÍP LÁI"
      self.current_mission = "Phòng thủ & Hồi sức"
      self.current_weather = random.choice(WEATHER_CONDITIONS)

    # 2. HỆ THỐNG MÁY ĐO CỰ LY (RANGEFINDER)
    elif action_type == "rangefinder":
      if not self.crew["commander"] and not self.crew["gunner"]:
        result_title = "❌ ĐO CỰ LY THẤT BẠI"
        extra_info = "Trưởng xe và Pháo thủ đã hy sinh! Không thể đo cự ly mục tiêu."
      elif self.has_lrf:
        self.aim_zeroing = self.locked_distance
        result_title = "📏 LZR RANGEFINDER: TỰ ĐỘNG KHÓA CỰ LY"
        extra_info = f"Máy đo cự ly Laser quét chính xác 100%! Thước ngắm tự khóa vào **{self.aim_zeroing}m**."
      else:
        self.aim_zeroing = round(self.locked_distance + random.randint(-250, 250), -1)
        result_title = "📏 MECH RANGEFINDER: ĐO CỰ LY THỦ CÔNG"
        extra_info = f"Đo cự ly quang học thủ công: Ước tính cự ly mục tiêu ở mức **{self.aim_zeroing}m**."

    elif action_type == "zero_up":
      self.aim_zeroing += 100
      result_title = "🔼 NÂNG THƯỚC NGẮM DÃ CHIẾN"
      extra_info = f"Đã nâng thước ngắm lên **{self.aim_zeroing}m**."

    elif action_type == "zero_down":
      self.aim_zeroing = max(0, self.aim_zeroing - 100)
      result_title = "🔽 HẠ THƯỚC NGẮM DÃ CHIẾN"
      extra_info = f"Đã hạ thước ngắm xuống **{self.aim_zeroing}m**."

    # 3. BẮN PHÁO CHÍNH / AUTOCANNON
    elif action_type == "fire":
      if not self.crew["gunner"]:
        extra_info += "\n⚠️ Pháo thủ hy sinh! Trưởng xe phải ngắm thay (Độ chính xác giảm)."

      diff = abs(self.aim_zeroing - self.locked_distance)
      if diff > 150 and random.randint(1, 100) > 25:
        result_title = "🎯 KHAI HỎA: BẮN TRƯỢT (LỆCH THƯỚC NGẮM)"
        extra_info = f"Đạn rơi sai cự ly do lệch thước ngắm (**{diff}m**)! Hãy điều chỉnh lại thước ngắm."
      else:
        if self.is_autocannon:
          shots = random.randint(3, 5)
          hits = sum(1 for _ in range(shots) if random.randint(1, 100) <= 80)
          damage_per_shot = random.randint(5, 8)
          total_dmg = hits * damage_per_shot
          
          if any(x in self.enemy_tank for x in ERA_TANKS) and random.randint(1, 100) <= 55:
            total_dmg = int(total_dmg * 0.3)
            extra_info = f"Nã liên thanh **{shots}** phát đạn! **Giáp ERA địch phát nổ giảm sát thương!** Gây **{total_dmg}% HP**."
          else:
            extra_info = f"Nã liên thanh **{shots}** phát đạn APDS! **{hits}** viên trúng mục tiêu, gây **{total_dmg}% HP** sát thương."
            
          enemy_dmg = total_dmg
          result_title = f"💥 AUTOCANNON: XẢ LIÊN THANH ({shots} VIÊN)"
        else:
          hit_type = random.choice(["HIT", "CRITICAL", "NON-PEN"])
          if hit_type == "NON-PEN":
            result_title = "🎯 KHAI HỎA: NON-PEN (BẬT GIÁP)"
            extra_info = "Đạn va chạm góc hiểm bị bật giáp ra ngoài!"
          else:
            base_dmg = random.randint(25, 45) if hit_type == "HIT" else random.randint(45, 65)
            if any(x in self.enemy_tank for x in ERA_TANKS) and random.randint(1, 100) <= 55:
              base_dmg = int(base_dmg * 0.3)
              result_title = f"🎯 KHAI HỎA: {hit_type} (GIÁP ERA ĐỊCH KÍCH HOẠT)"
              extra_info = f"Giáp phản ứng nổ ERA của địch phát nổ triệt tiêu 70% sát thương! Chỉ gây **-{base_dmg}% HP**."
            else:
              result_title = f"🎯 KHAI HỎA: {hit_type}"
              extra_info = f"Đạn xuyên thẳng giáp xe địch! Gây **-{base_dmg}% HP**."
            enemy_dmg = base_dmg

    # 4. TÊN LỬA ATGM (BẢO VỆ BỞI APS / IRCM / ERA ĐỊCH)
    elif action_type == "atgm":
      if not self.crew["gunner"]:
        result_title = "🚀 ATGM: BẮN TRƯỢT"
        extra_info = "Pháo thủ hy sinh, không thể dẫn đường tên lửa!"
      else:
        if any(x in self.enemy_tank for x in APS_TANKS) and random.randint(1, 100) <= 25:
          result_title = "🚀 ATGM: BỊ HỆ THỐNG APS ĐỊCH ĐÁNH CHẶN"
          extra_info = f"Hệ thống APS của **{self.enemy_tank.upper()}** phát hiện và bắn hạ ATGM trên không!"
        elif any(x in self.enemy_tank for x in IRCM_TANKS) and random.randint(1, 100) <= 35:
          result_title = "🚀 ATGM: BỊ LÀM NHIỄU BỞI IRCM"
          extra_info = f"Đèn hồng ngoại IRCM của **{self.enemy_tank.upper()}** làm mất tín hiệu dẫn đường tên lửa!"
        else:
          dmg_atgm = random.randint(35, 55)
          if any(x in self.enemy_tank for x in ERA_TANKS) and random.randint(1, 100) <= 55:
            dmg_atgm = int(dmg_atgm * 0.3)
            result_title = "🚀 ATGM TRÚNG MỤC TIÊU (GIÁP ERA ĐỊCH KÍCH HOẠT)"
            extra_info = f"Giáp ERA của địch nổ tung triệt tiêu đầu đạn nổ lõm! Chỉ gây **-{dmg_atgm}% HP**."
          else:
            result_title = "🚀 ATGM: BẮN TRÚNG MỤC TIÊU CHÍ MẠNG"
            extra_info = f"Tên lửa ATGM xuyên thủng giáp chính xe địch! Gây **-{dmg_atgm}% HP**."
          enemy_dmg = dmg_atgm

    # 5. TRINH SÁT ỐNG NHÒM
    elif action_type == "binocular":
      if not self.crew["commander"]:
        result_title = "🔭 QUAN SÁT THẤT BẠI"
        extra_info = "Trưởng xe đã hy sinh! Không thể quan sát qua ống nhòm."
      else:
        self.locked_distance = random.randint(400, 2800)
        num_enemies = random.randint(1, 3)
        enemy_lines = []
        for i in range(1, num_enemies + 1):
          e_hp = random.choice([40, 70, 100])
          e_bar = "█" * (e_hp // 20) + "░" * (5 - (e_hp // 20))
          e_name = random.choice(["T-72B3", "Leopard 2", "M1A1 Abrams", "BMP-2"])
          enemy_lines.append(f" địch #{i} [{e_name}] | HP: [{e_bar}] {e_hp}%")

        result_title = "🔭 QUAN SÁT ỐNG NHÒM (TRINH SÁT)"
        self.enemy_status_text = "\n".join(enemy_lines)
        extra_info = f"Đã quét mục tiêu qua kính trinh sát ở cự ly **{self.locked_distance}m**."
        self.current_mission = "Tiêu diệt kẻ địch"

    # 6. CƠ ĐỘNG
    elif action_type == "move_forward":
      if not self.crew["driver"]:
        result_title = "❌ CƠ ĐỘNG THẤT BẠI"
        extra_info = "Lái xe đã hy sinh! Xe tăng đứng yên không thể tiến lên."
      else:
        self.speed = "Tiến lên tuyến đầu"
        result_title = "🏎️ CƠ ĐỘNG: TIẾN LÊN"
        extra_info = "Tăng tốc vượt chướng ngại vật, tạo góc khai hỏa mới."
        self.current_mission = "Tiên phong đột phá"

    elif action_type == "move_backward":
      if not self.crew["driver"]:
        result_title = "❌ CƠ ĐỘNG THẤT BẠI"
        extra_info = "Lái xe đã hy sinh! Xe tăng đứng yên không thể lùi."
      else:
        self.speed = "Lùi về ẩn nấp"
        result_title = "🔙 CƠ ĐỘNG: LÙI VỀ"
        extra_info = "Rút lui về sau gờ đất né làn đạn."
        self.current_mission = "Trinh sát chiến tuyến"

    # 7. SỬA CHỮA DÃ CHIẾN
    elif action_type == "repair":
      self.repair_cooldown = 2
      self.speed = "Đang đứng sửa chữa dã chiến"
      result_title = "🛠️ SỬA CHỮA DÃ CHIẾN"
      heal_amount = random.randint(20, 35)
      self.hp = min(100, self.hp + heal_amount)
      
      dead_crew = [k for k, v in self.crew.items() if not v]
      if dead_crew:
        revived = dead_crew[0]
        self.crew[revived] = True
        extra_info = f"Hàn gắn giáp dã chiến, hồi phục **+{heal_amount}% HP** và sơ cứu cho 1 thành viên kíp lái!"
      else:
        extra_info = f"Hàn gắn khung gầm dã chiến, hồi phục **+{heal_amount}% HP**!"
      self.current_mission = "Sửa chữa & Phòng thủ"

    weather_cleared = self.check_weather_cycle()
    if weather_cleared:
      extra_info += "\n⛅ **Bầu trời chuyển biến:** Bão tố/Đêm tối đã chấm dứt!"

    # KẺ ĐỊCH PHẢN CÔNG (APS / IRCM / ERA XE PLAYER)
    if action_type not in ["move_backward", "repair", "rest"] and enemy_dmg < 100 and self.hp > 0:
      enemy_action_is_atgm = random.randint(1, 100) <= 40
      hit_taken = random.randint(15, 45)
      
      if enemy_action_is_atgm:
        if self.has_aps and random.randint(1, 100) <= 25:
          extra_info += "\n\n🛡️ **HỆ THỐNG APS KÍCH HOẠT:** Đã bắn hạ thành công tên lửa ATGM của địch!"
          hit_taken = 0
        elif self.has_ircm and random.randint(1, 100) <= 35:
          extra_info += "\n\n💡 **HỆ THỐNG IRCM KHỞI ĐỘNG:** Đèn hồng ngoại làm nhiễu khiến ATGM địch bắn trượt!"
          hit_taken = 0

      if hit_taken > 0:
        if self.has_era and random.randint(1, 100) <= 55:
          hit_taken = int(hit_taken * 0.3)
          extra_info += f"\n\n🧱 **GIÁP ERA PHÁT NỔ:** Triệt tiêu đòn đánh! Chỉ nhận **{hit_taken}%** sát thương."
        else:
          extra_info += f"\n\n⚠️ **KẺ ĐỊCH PHẢN CÔNG:** Gây ra {hit_taken}% sát thương!"

        self.hp = max(0, self.hp - hit_taken)
        extra_info += self.apply_random_crew_casualty()

    if self.hp <= 0:
      self.current_mission = "Đã bị bắn hạ (Wrecked)"
      result_title = "❌ CHIẾN TRƯỜNG KẾT THÚC"

    prompt = (
        f"Sĩ quan thực hiện '{action_desc}' trong thời tiết {self.current_weather['name']}. "
        f"{extra_info}. Nhiệm vụ hiện tại: {self.current_mission}. "
        "Hãy phân tích thông số kỹ thuật ngắn gọn qua giao diện FCS."
    )
    report = "Hệ thống FCS hoạt động ổn định."

    if ai_client:
      try:
        response = ai_client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt,
            config=types.GenerateContentConfig(system_instruction=YURI_MILITARY_SYSTEM_PROMPT),
        )
        if response and response.text:
          report = response.text.strip()
      except Exception as e:
        print(f"🔥 Gemini Error: {e}")

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
        self.aim_zeroing,
        self.current_weather["name"],
        self.action_counter,
        self.crew,
        self.has_lrf,
        self.get_defense_string(self.tank_name)
    )

    if self.hp <= 0:
      embed_color = discord.Color.red()
    elif "NON-PEN" in result_title or "MISS" in result_title:
      embed_color = discord.Color.orange()
    else:
      embed_color = discord.Color.dark_red()

    embed = discord.Embed(
        title=result_title,
        description=f"> 🗡️ *\"{report}\"*\n\n```text\n{screen_art}\n```",
        color=embed_color,
    )
    embed.add_field(name="🛡️ Khí tài", value=f"`{self.tank_name.upper()}`", inline=True)
    embed.add_field(name="❤️ HP Hiện tại", value=f"**{self.hp}%**", inline=True)
    embed.add_field(name="🌦️ Thời tiết", value=self.current_weather["name"], inline=True)

    if self.hp <= 0:
      embed.add_field(name="⚠️ Trạng thái", value="❌ **Đã bị tiêu diệt hoàn toàn!**", inline=False)
      self.clear_items()

    await interaction.message.edit(embed=embed, view=self)

  @discord.ui.button(label="🎯 Khai hoả", style=discord.ButtonStyle.danger, row=0)
  async def btn_fire(self, interaction: discord.Interaction, button: discord.ui.Button):
    await self.execute_action(interaction, "fire", "Khai hỏa pháo chính")

  @discord.ui.button(label="🚀 Tên lửa ATGM", style=discord.ButtonStyle.danger, row=0)
  async def btn_atgm(self, interaction: discord.Interaction, button: discord.ui.Button):
    await self.execute_action(interaction, "atgm", "Phóng tên lửa chống tăng ATGM")

  @discord.ui.button(label="📏 Máy đo cự ly", style=discord.ButtonStyle.primary, row=0)
  async def btn_rf(self, interaction: discord.Interaction, button: discord.ui.Button):
    await self.execute_action(interaction, "rangefinder", "Sử dụng máy đo cự ly")

  @discord.ui.button(label="🔼 Nâng nòng (+100m)", style=discord.ButtonStyle.secondary, row=1)
  async def btn_zero_up(self, interaction: discord.Interaction, button: discord.ui.Button):
    await self.execute_action(interaction, "zero_up", "Nâng thước ngắm")

  @discord.ui.button(label="🔽 Hạ nòng (-100m)", style=discord.ButtonStyle.secondary, row=1)
  async def btn_zero_down(self, interaction: discord.Interaction, button: discord.ui.Button):
    await self.execute_action(interaction, "zero_down", "Hạ thước ngắm")

  @discord.ui.button(label="🔭 Quan sát", style=discord.ButtonStyle.primary, row=1)
  async def btn_binocular(self, interaction: discord.Interaction, button: discord.ui.Button):
    await self.execute_action(interaction, "binocular", "Sử dụng ống nhòm trinh sát")

  @discord.ui.button(label="🛠️ Sửa chữa", style=discord.ButtonStyle.secondary, row=2)
  async def btn_repair(self, interaction: discord.Interaction, button: discord.ui.Button):
    await self.execute_action(interaction, "repair", "Tiến hành sửa chữa dã chiến")

  @discord.ui.button(label="🏕️ Nghỉ ngơi", style=discord.ButtonStyle.success, row=2)
  async def btn_rest(self, interaction: discord.Interaction, button: discord.ui.Button):
    await self.execute_action(interaction, "rest", "Nghỉ ngơi, thay thế kíp lái hy sinh và cắm trại")

  @discord.ui.button(label="🚀 Tiến lên", style=discord.ButtonStyle.success, row=2)
  async def btn_forward(self, interaction: discord.Interaction, button: discord.ui.Button):
    await self.execute_action(interaction, "move_forward", "Tiến lên tuyến đầu")

  @discord.ui.button(label="🔙 Lùi về", style=discord.ButtonStyle.secondary, row=2)
  async def btn_backward(self, interaction: discord.Interaction, button: discord.ui.Button):
    await self.execute_action(interaction, "move_backward", "Lùi về vị trí an toàn")


# ================= 5. CÁC LỆNH BOT & SỰ KIỆN CHAT =================
@bot.event
async def on_message(message):
  if message.author == bot.user:
    return

  if bot.user.mentioned_in(message) and not message.content.startswith("!"):
    user_query = message.content.replace(f"<@!{bot.user.id}>", "").replace(f"<@{bot.user.id}>", "").strip()
    if not user_query:
      user_query = "Yuri đang làm gì thế?"

    prompt = f"Đồng chí Nam hỏi bạn tại doanh trại: '{user_query}'. Hãy trả lời cực kỳ ngắn gọn, sắc sảo theo đúng tính cách DDLC."

    async with message.channel.typing():
      reply_text = "Hệ thống tư duy đang khởi động..."
      if ai_client:
        try:
          response = ai_client.models.generate_content(
              model='gemini-2.0-flash',
              contents=prompt,
              config=types.GenerateContentConfig(
                  system_instruction=YURI_MILITARY_SYSTEM_PROMPT
              ),
          )
          if response and response.text:
            reply_text = response.text.strip()
        except Exception as e:
          print(f"🔥 Gemini Error: {e}")

    await message.reply(f"🗡️ *\"{reply_text}\"*\n- - -\n*{message.author.display_name}*")
    return

  await bot.process_commands(message)

@bot.command(name="Yhelps")
async def y_helps(ctx):
  embed = discord.Embed(
      title="📜 SỔ TAY CHIẾN DỊCH & MINIGAME WAR THUNDER",
      description=(
          "1. `!campaign` - Mở bản đồ chiến dịch\n"
          "2. `!Yteam [Nga/Uka]` - Chọn phe quân sự\n"
          "3. `!deploy [tên xe]` - Xuất chiến khí tài\n"
          "4. `!fcs` - Mở giao diện tác chiến điện tử FCS\n"
          "5. `!Ysleep` - Đi ngủ nhanh (skip hội thoại, bổ sung kíp lái)\n"
          "6. `!Yguess [số]` - Minigame pháo thủ: Đoán cự ly mục tiêu (1-100m)"
      ),
      color=discord.Color.dark_red(),
  )
  await ctx.send(embed=embed)

@bot.command(name="Yguess")
async def y_guess(ctx, guess: int = None):
  guild_id = ctx.guild.id

  if guess is None:
    target_distance = random.randint(10, 100)
    active_guesses[guild_id] = target_distance
    embed = discord.Embed(
        title="🎯 MINIGAME: ĐOÁN CỰ LY MỤC TIÊU",
        description=(
            "Yuri nheo mắt ngắm qua kính tiềm vọng: '*Mục tiêu địch xuất hiện trong khoảng **1 đến 100 mét**!*\n"
            "Hãy gõ **`!Yguess [số mét]`** để nã pháo căn chỉnh cự ly ngay!*'"
        ),
        color=discord.Color.blue(),
    )
    return await ctx.send(embed=embed)

  if guild_id not in active_guesses:
    active_guesses[guild_id] = random.randint(10, 100)

  target = active_guesses[guild_id]

  if guess == target:
    del active_guesses[guild_id]
    embed = discord.Embed(
        title="💥 BẮN TRÚNG HỒ ĐIỂM (DIRECT HIT!)",
        description=f"Yuri mỉm cười sắc lạnh: '*Tuyệt vời! Cự ly chính xác tuyệt đối **{target}m**. Địch đã bay màu!*'",
        color=discord.Color.green(),
    )
  elif guess < target:
    embed = discord.Embed(
        title="📉 ĐẠN RƠI THẤP (UNDER)",
        description=f"Yuri lắc đầu: '*Mục tiêu ở xa hơn **{guess}m** đấy, nâng thước ngắm lên!*'",
        color=discord.Color.orange(),
    )
  else:
    embed = discord.Embed(
        title="📈 ĐẠN BAY QUÁ (OVER)",
        description=f"Yuri chớp mắt: '*Xa quá rồi, giảm thước ngắm xuống dưới **{guess}m** đi!*'",
        color=discord.Color.orange(),
    )

  await ctx.send(embed=embed)

@bot.command(name="Ysleep")
async def y_sleep(ctx):
  guild_id = ctx.guild.id
  if guild_id not in game_sessions or not game_sessions[guild_id].get("tanks"):
    return await ctx.send("⚠️ Bạn chưa triển khai xe tăng nào ra chiến trường!")

  ambush_chance = 45
  hit_by_enemy = random.randint(1, 100) <= ambush_chance
  heal_amount = random.randint(20, 40)

  msg = "🏕️ **[!YSLEEP]** Kíp chiến đấu chợp mắt nghỉ ngơi dã chiến...\n"
  if hit_by_enemy:
    dmg = random.randint(15, 35)
    msg += f"⚠️ **KẺ ĐỊCH PHỤC KÍCH: Gây ra {dmg}% sát thương!**\n"
  else:
    msg += f"🛡️ Nghỉ ngơi an toàn! Hồi phục thành công **+{heal_amount}% HP**.\n"

  msg += "👨‍✈️ **BỔ SUNG LỰC LƯỢNG:** Đã chữa trị và thay thế toàn bộ thành viên kíp lái hy sinh!"

  embed = discord.Embed(
      title="💤 NGỦ QUA ĐÊM (RECOVER & REFILL CREW)",
      description=msg,
      color=discord.Color.orange() if hit_by_enemy else discord.Color.green(),
  )
  await ctx.send(embed=embed)

@bot.command(name="campaign")
async def campaign(ctx):
  guild_id = ctx.guild.id
  game_sessions[guild_id] = {"team": None, "tanks": []}
  embed = discord.Embed(
      title="🌐 MẶT TRẬN ĐÔNG ÂU",
      description=(
          "Yuri đẩy gọng kính: '*Chọn phe ngay nhé đồng chí: **`!Yteam Nga`**"
          " hoặc **`!Yteam Uka`**!*'"
      ),
      color=discord.Color.red(),
  )
  await ctx.send(embed=embed)

@bot.command(name="Yteam")
async def y_team(ctx, team_name: str):
  guild_id = ctx.guild.id
  team_lower = team_name.capitalize()
  if team_lower not in ["Nga", "Uka"]:
    return await ctx.send(
        "⚠️ Chọn sai phe! Dùng: `!Yteam Nga` hoặc `!Yteam Uka`."
    )

  if guild_id not in game_sessions:
    game_sessions[guild_id] = {"tanks": []}
  game_sessions[guild_id]["team"] = team_lower
  tanks = ", ".join([f"`{t}`" for t in TEAM_TANKS[team_lower]])

  embed = discord.Embed(
      title=f"🎖️ ĐÃ CHỌN PHE: {team_lower.upper()}",
      description=(
          f"Khí tài trong kho: {tanks}\n\nGõ `!deploy [tên xe]` để xuất chiến!"
      ),
      color=discord.Color.blue(),
  )
  await ctx.send(embed=embed)

@bot.command(name="deploy")
async def deploy(ctx, tank_model: str, sector: str = "Tuyến đầu"):
  guild_id = ctx.guild.id
  if guild_id not in game_sessions or not game_sessions[guild_id].get("team"):
    return await ctx.send(
        "⚠️ Chưa chọn phe! Gõ `!campaign` rồi `!Yteam` trước."
    )

  current_team = game_sessions[guild_id]["team"]
  if tank_model.lower() not in TEAM_TANKS[current_team]:
    return await ctx.send(
        f"❌ Xe `{tank_model}` không thuộc biên chế phe {current_team}!"
    )

  game_sessions[guild_id]["tanks"].append(
      {"model": tank_model.lower(), "sector": sector}
  )
  await ctx.send(
      f"🛡️ Triển khai thành công **{tank_model.upper()}** tại {sector}! Gõ `!fcs` để"
      " mở giao diện tác chiến."
  )

@bot.command(name="fcs")
async def fcs(ctx):
  guild_id = ctx.guild.id
  tank_model = "t-90m"
  if guild_id in game_sessions and game_sessions[guild_id]["tanks"]:
    tank_model = game_sessions[guild_id]["tanks"][-1]["model"]

  fcs_mode = (
      "basic"
      if any(x in tank_model.lower() for x in ["bmp-2", "bradley", "puma"])
      else "t72"
  )
  view = QuickChatFCSView(ctx, tank_model)
  initial_screen = generate_fcs_view(
      tank_model,
      fcs_mode,
      speed="Đứng yên",
      ammo=view.ammo,
      hp=100,
      mission="Tiêu diệt địch",
      weather=view.current_weather["name"],
      action_counter=view.action_counter,
      crew_status=view.crew,
      has_lrf=view.has_lrf,
      defenses_info=view.get_defense_string(tank_model)
  )
  embed = discord.Embed(
      title="🔭 HỆ THỐNG TÁC CHIẾN TỔNG HỢP WAR THUNDER FCS",
      description=(
          f"Yuri: '*Bắt đầu tác chiến với **{tank_model.upper()}**!*'\n```text\n"
          f"{initial_screen}\n```"
      ),
      color=discord.Color.dark_purple(),
  )
  await ctx.send(embed=embed, view=view)

@bot.event
async def on_ready():
  print(f"✅ Yuri War Thunder Uncut Master Bot đã sẵn sàng: {bot.user.name}")

if __name__ == "__main__":
  keep_alive()
  if DISCORD_TOKEN:
    bot.run(DISCORD_TOKEN)
  else:
    print("❌ LỖI: Chưa cấu hình DISCORD_TOKEN trong biến môi trường!")
