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
  return "War Thunder Yuri Bot - Full Operational Command System Active."

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

# Dữ liệu bộ nhớ tạm cho Session game & Minigame
game_sessions = {}
active_guesses = {}
user_profiles = {}

# Danh sách xe theo phe
TEAM_TANKS = {
    "Nga": ["t-80", "t-90a", "bmp-3", "bmpt", "t-90m", "t-72b3m", "t-64bv"],
    "Uka": ["m1a1-abrams", "leopard-2a7", "bradley-tusk", "puma", "bmp-2", "t-72b3"],
}

# Đặc tính kỹ thuật xe
LASER_RF_TANKS = ["t-90m", "t-90a", "t-72b3m", "t-80", "leopard-2a7", "m1a1-abrams", "puma", "bmpt"]
ATGM_TANKS = ["t-80", "t-90a", "t-90m", "t-72b3m", "bmp-2", "bmp-3", "bradley-tusk", "t-64bv", "bmpt"]
AUTOCANNON_TANKS = ["bmp-2", "bmp-3", "bradley-tusk", "puma", "bmpt"]

APS_TANKS = ["t-90m"]
IRCM_TANKS = ["puma", "t-90a", "t-90m"]
ERA_TANKS = ["t-80", "t-90a", "t-90m", "t-72b3m", "t-72b3", "t-64bv", "bradley-tusk"]

YURI_MILITARY_SYSTEM_PROMPT = (
    "Bạn là Yuri - Sĩ quan tham mưu kiêm pháo thủ thiết giáp trong game War Thunder. "
    "Phong cách sắc lạnh, trầm lặng, phảng phất nét nội tâm sắc bén đặc trưng của Yuri (DDLC). "
    "Bạn xưng呼 người chơi là 'Chỉ huy Nam' hoặc 'Đồng chí Nam'. "
    "Nói ngắn gọn (dưới 3 câu), tập trung phân tích kỹ thuật góc bắn, thiệt hại kíp lái, thông số đa mục tiêu."
)

WEATHER_CONDITIONS = [
    {"name": "☀️ Ban ngày quang đãng", "requires_rest": False, "vis_mod": 1.0},
    {"name": "🌧️ Bão tố sấm sét", "requires_rest": True, "vis_mod": 0.7},
    {"name": "🌙 Trời tối mịt mờ", "requires_rest": True, "vis_mod": 0.6},
    {"name": "🌫️ Sương mù dày đặc", "requires_rest": False, "vis_mod": 0.8},
]

# ================= 3. HÀM HIỂN THỊ HỆ THỐNG FCS MỞ RỘNG (MULTI-TARGET) =================
def generate_fcs_view(
    tank_name,
    fcs_type="t72",
    speed="Đứng yên",
    ammo="APFSDS",
    hp=100,
    enemies=None,
    active_target_idx=0,
    mission="Tiêu diệt toàn bộ lực lượng địch",
    enemy_info="",
    cooldown_turns=0,
    aim_zeroing=1650,
    weather="☀️ Ban ngày quang đãng",
    action_counter=0,
    crew_status=None,
    has_lrf=False,
    defenses_info="",
    has_steel_hearts=False,
    has_freedom_forever=False,
    retreat_charges=0
):
  if enemies is None:
    enemies = [{"name": "T-72B3", "hp": 100, "distance": 1500}]

  hp_bar = "█" * (hp // 20) + "░" * (5 - (hp // 20))

  if crew_status is None:
    crew_status = {"commander": True, "gunner": True, "driver": True, "loader": True}

  c_str = "🟢" if crew_status["commander"] else "❌"
  g_str = "🟢" if crew_status["gunner"] else "❌"
  d_str = "🟢" if crew_status["driver"] else "❌"
  l_str = "🟢" if crew_status["loader"] else "❌"

  lrf_str = " [LRF: AUTO]" if has_lrf else " [MECH: MANUAL]"
  
  trait_str = ""
  if has_steel_hearts:
    trait_str = " [🔥 STEEL HEARTS]"
  elif has_freedom_forever:
    trait_str = f" [🕊️ FREEDOM FOREVER ({retreat_charges} Safe Lùi)]"

  # Hiển thị danh sách kẻ địch đa mục tiêu
  enemy_display_lines = []
  for idx, e in enumerate(enemies):
    e_hp_bar = "█" * (max(0, e["hp"]) // 20) + "░" * (5 - (max(0, e["hp"]) // 20))
    pointer = "👉 [LOCK]" if idx == active_target_idx else f"   [#{idx+1}]"
    if e["hp"] <= 0:
      enemy_display_lines.append(f"{pointer} {e['name'].upper()} - 💀 ĐÃ BỊ TIÊU DIỆT")
    else:
      enemy_display_lines.append(f"{pointer} {e['name'].upper()} | HP: [{e_hp_bar}] {max(0, e['hp'])}% | Cự ly: {e['distance']}m")

  enemies_text = "\n".join(enemy_display_lines)

  screen = f"""[BATTLEFIELD] Thời tiết: {weather} | Chu kỳ: {action_counter}/4{trait_str}
[FCS: {tank_name.upper()} - {fcs_type.upper()}] | MÁU XE TA: [{hp_bar}] {hp}%
⚙️ Trạng thái cơ động: {speed} | 📦 Băng đạn: {ammo}
🛡️ Mạng lưới bảo vệ: {defenses_info}
👨‍✈️ Kíp xe: [Trưởng xe: {c_str} | Pháo thủ: {g_str} | Lái xe: {d_str} | Nạp đạn: {l_str}]
--------------------------------------------------
🎯 MỤC TIÊU PHÁT HIỆN TRÊN MÀN HÌNH TÁC CHIẾN:
{enemies_text}
--------------------------------------------------
📐 Cài đặt thước ngắm: {aim_zeroing}m{lrf_str}
🎯 Nhiệm vụ chính: {mission}"""

  if hp <= 0:
    screen += "\n❌ XE TĂNG BỊ PHÁ HỦY HOẶC KÍP LÁI BỊ VÔ HIỆU HÓA!"
  elif all(e["hp"] <= 0 for e in enemies):
    screen += "\n🎉 TOÀN BỘ MỤC TIÊU ĐỊCH ĐÃ BỊ BẮN HẠ!"
  elif cooldown_turns > 0:
    screen += f"\n⚠️ TRẠNG THÁI: Đang khắc phục sự cố dã chiến (Còn {cooldown_turns} lượt)"

  return screen

# ================= 4. GIAO DIỆN NÚT BẤM TƯƠNG TÁC TỐI ƯU HÓA =================
class QuickChatFCSView(discord.ui.View):

  def __init__(self, ctx, tank_name, team_name="Nga"):
    super().__init__(timeout=300)
    self.ctx = ctx
    self.tank_name = tank_name.lower()
    self.team_name = team_name
    self.fcs_type = "basic" if any(x in self.tank_name for x in ["bmp-2", "bradley", "puma"]) else "t72"
    self.speed = "Đứng yên ngắm bắn"
    self.ammo = "APFSDS" if self.tank_name not in AUTOCANNON_TANKS else "APDS Autocannon"
    self.hp = 100
    
    # Khởi tạo đa mục tiêu (2 đến 3 xe tăng)
    num_enemies = random.randint(2, 3)
    possible_enemies = ["t-90m", "t-90a", "m1a1-abrams", "leopard-2a7", "bradley-tusk", "puma", "t-72b3"]
    self.enemies = []
    for _ in range(num_enemies):
      self.enemies.append({
          "name": random.choice(possible_enemies),
          "hp": 100,
          "distance": random.randint(900, 2500)
      })
    
    self.active_target_idx = 0
    self.current_mission = "Quét sạch mọi mối đe dọa thiết giáp"
    self.enemy_status_text = ""
    self.repair_cooldown = 0
    self.aim_zeroing = 1000
    self.current_weather = random.choice(WEATHER_CONDITIONS)
    self.action_counter = 0

    # Trang bị xe
    self.has_lrf = any(x in self.tank_name for x in LASER_RF_TANKS)
    self.has_atgm = any(x in self.tank_name for x in ATGM_TANKS)
    self.is_autocannon = any(x in self.tank_name for x in AUTOCANNON_TANKS)
    self.has_aps = any(x in self.tank_name for x in APS_TANKS)
    self.has_ircm = any(x in self.tank_name for x in IRCM_TANKS)
    self.has_era = any(x in self.tank_name for x in ERA_TANKS)

    self.has_steel_hearts = False
    self.has_freedom_forever = False
    self.retreat_charges = 0

    if self.team_name == "Nga":
      self.has_steel_hearts = random.randint(1, 100) <= 30
    elif self.team_name == "Uka":
      self.has_freedom_forever = True
      self.retreat_charges = 2

    self.crew = {"commander": True, "gunner": True, "driver": True, "loader": True}

    if not self.has_atgm:
      self.remove_item(self.btn_atgm)

  def get_defense_string(self, tank_n):
    defs = []
    if any(x in tank_n for x in APS_TANKS): defs.append("APS (25%)")
    if any(x in tank_n for x in IRCM_TANKS): defs.append("IRCM (35%)")
    if any(x in tank_n for x in ERA_TANKS): defs.append("ERA (25%)")
    return " | ".join(defs) if defs else "Giáp thép cán tiêu chuẩn"

  def check_weather_cycle(self):
    self.action_counter += 1
    if self.action_counter >= 4:
      self.action_counter = 0
      if "Bão tố" in self.current_weather["name"] or "Trời tối" in self.current_weather["name"]:
        if random.randint(1, 100) <= 70:
          self.current_weather = {"name": "☀️ Ban ngày quang đãng", "requires_rest": False, "vis_mod": 1.0}
          return True
    return False

  def check_crew_status(self):
    alive_count = sum(1 for v in self.crew.values() if v)
    if alive_count <= 1:
      self.hp = 0
      return True
    return False

  def apply_random_crew_casualty(self):
    alive_crew = [k for k, v in self.crew.items() if v]
    if alive_crew and random.randint(1, 100) <= 35:
      casualty = random.choice(alive_crew)
      self.crew[casualty] = False
      names = {"commander": "Trưởng xe", "gunner": "Pháo thủ", "driver": "Lái xe", "loader": "Nạp đạn viên"}
      msg = f"\n⚠️ **THƯƠNG VONG KÍP XE:** {names[casualty]} bị loại khỏi vòng chiến!"
      if self.check_crew_status():
        msg += "\n❌ **TỔN THẤT NGHIÊM TRỌNG:** Kíp xe không đủ người vận hành!"
      return msg
    return ""

  async def execute_action(self, interaction: discord.Interaction, action_type, action_desc):
    if interaction.user != self.ctx.author:
      return await interaction.response.send_message("⚠️ Chỉ huy ra lệnh chiến đấu mới có quyền điều khiển FCS!", ephemeral=True)

    if self.hp <= 0:
      return await interaction.response.send_message("❌ Xe đã bị tiêu diệt, không thể thao tác!", ephemeral=True)

    if all(e["hp"] <= 0 for e in self.enemies):
      return await interaction.response.send_message("🎉 Toàn bộ kẻ địch đã bị quét sạch!", ephemeral=True)

    # Chuyển target nếu target cũ đã gục
    if self.enemies[self.active_target_idx]["hp"] <= 0:
      for idx, e in enumerate(self.enemies):
        if e["hp"] > 0:
          self.active_target_idx = idx
          break

    target_enemy = self.enemies[self.active_target_idx]

    is_severe_weather = self.current_weather["requires_rest"] and not self.has_steel_hearts
    if is_severe_weather and action_type not in ["rest", "cycle_target"]:
      return await interaction.response.send_message(
          f"⚠️ Thời tiết **{self.current_weather['name']}** tầm nhìn hạn chế! Bắt buộc dùng **[🏕️ Nghỉ ngơi]**.",
          ephemeral=True,
      )

    await interaction.response.defer()

    extra_info = ""
    result_title = ""
    damage_dealt = 0
    safe_retreat_activated = False

    # Logic thao tác
    if action_type == "cycle_target":
      self.active_target_idx = (self.active_target_idx + 1) % len(self.enemies)
      new_t = self.enemies[self.active_target_idx]
      result_title = "🔄 ĐỔI MỤC TIÊU KHÓA"
      extra_info = f"Chuyển ngắm FCS sang mục tiêu **#{self.active_target_idx+1} ({new_t['name'].upper()})** - Cự ly: {new_t['distance']}m."

    elif action_type == "rest":
      if random.randint(1, 100) <= 40:
        dmg = random.randint(10, 20)
        self.hp = max(0, self.hp - dmg)
        extra_info = f"⚠️ Bị địch tập kích trong lúc dừng nghỉ! Mất -{dmg}% HP."
      else:
        extra_info = "🛡️ Tạm dừng củng cố đội hình an toàn."

      heal = random.randint(20, 35)
      self.hp = min(100, self.hp + heal)
      self.crew = {"commander": True, "gunner": True, "driver": True, "loader": True}
      extra_info += f"\n🏕️ Đã bổ sung kíp xe và khắc phục **+{heal}% HP**."
      result_title = "🏕️ NGHỈ NGƠI DÃ CHIẾN"

    elif action_type == "rangefinder":
      if self.has_lrf:
        self.aim_zeroing = target_enemy["distance"]
        result_title = "📏 LASE RANGEFINDER"
        extra_info = f"Khóa cự ly mục tiêu #{self.active_target_idx+1}: **{self.aim_zeroing}m** chính xác."
      else:
        self.aim_zeroing = round(target_enemy["distance"] + random.randint(-180, 180), -1)
        result_title = "📏 ƯỚC LƯỢNG CỰ LY"
        extra_info = f"Ước tính cự ly mục tiêu #{self.active_target_idx+1}: **{self.aim_zeroing}m**."

    elif action_type == "zero_up":
      self.aim_zeroing += 100
      result_title = "🔼 TĂNG THƯỚC NGẮM"
      extra_info = f"Điều chỉnh thước ngắm: **{self.aim_zeroing}m**."

    elif action_type == "zero_down":
      self.aim_zeroing = max(0, self.aim_zeroing - 100)
      result_title = "🔽 GIẢM THƯỚC NGẮM"
      extra_info = f"Điều chỉnh thước ngắm: **{self.aim_zeroing}m**."

    elif action_type == "fire":
      diff = abs(self.aim_zeroing - target_enemy["distance"])
      if diff > 150 and random.randint(1, 100) > 30:
        result_title = "🎯 KHAI HỎA: KHÔNG TRÚNG"
        extra_info = f"Đạn bay chệch mục tiêu #{self.active_target_idx+1} do lệch {diff}m cự ly!"
      else:
        if self.is_autocannon:
          shots = random.randint(4, 6)
          hits = sum(1 for _ in range(shots) if random.randint(1, 100) <= 80)
          damage_dealt = hits * random.randint(6, 9)
          if self.has_freedom_forever: damage_dealt = int(damage_dealt * 1.15)
          result_title = f"💥 XẢ SÚNG PHÁO TỰ ĐỘNG (Mụctiêu #{self.active_target_idx+1})"
          extra_info = f"Bắn trúng **{hits}/{shots}** đạn vào {target_enemy['name'].upper()}! Gây **-{damage_dealt}% HP**."
        else:
          damage_dealt = random.randint(35, 60)
          if self.has_freedom_forever: damage_dealt = int(damage_dealt * 1.15)
          result_title = f"🎯 BẮN TRÚNG MỤC TIÊU #{self.active_target_idx+1}"
          extra_info = f"Đạn xuyên thẳng vào {target_enemy['name'].upper()}! Gây **-{damage_dealt}% HP**."

    elif action_type == "atgm":
      damage_dealt = random.randint(45, 70)
      if self.has_freedom_forever: damage_dealt = int(damage_dealt * 1.15)
      result_title = f"🚀 PHÓNG TÊN LỬA ATGM (Mụctiêu #{self.active_target_idx+1})"
      extra_info = f"Tên lửa dẫn đường diệt gọn {target_enemy['name'].upper()}! Gây **-{damage_dealt}% HP**."

    elif action_type == "move_forward":
      self.speed = "Tiến công tốc độ cao"
      result_title = "🏎️ CƠ ĐỘNG: TIẾN LÊN"
      extra_info = "Áp sát trận địa địch."

    elif action_type == "move_backward":
      self.speed = "Lùi về vật cản"
      result_title = "🔙 CƠ ĐỘNG: LÙI VỀ"
      if self.has_freedom_forever and self.retreat_charges > 0:
        self.retreat_charges -= 1
        safe_retreat_activated = True
        extra_info = f"🕊️ **FREEDOM FOREVER:** Lùi an toàn tránh hoàn toàn đạn phản công! (Còn {self.retreat_charges} lần)"
      else:
        extra_info = "Rút lui tìm góc núp."

    elif action_type == "repair":
      self.repair_cooldown = 1
      heal = random.randint(15, 25)
      self.hp = min(100, self.hp + heal)
      result_title = "🛠️ SỬA CHỮA DÃ CHIẾN"
      extra_info = f"Đã khắc phục hỏng hóc, hồi phục **+{heal}% HP**."

    # Xử lý máu kẻ địch
    if damage_dealt > 0:
      target_enemy["hp"] = max(0, target_enemy["hp"] - damage_dealt)
      if target_enemy["hp"] <= 0:
        extra_info += f"\n💀 **Mục tiêu #{self.active_target_idx+1} ({target_enemy['name'].upper()}) bị tiêu diệt!**"
        for idx, e in enumerate(self.enemies):
          if e["hp"] > 0:
            self.active_target_idx = idx
            break

    # Kẻ địch phản công
    alive_enemies = [e for e in self.enemies if e["hp"] > 0]
    if action_type not in ["repair", "rest"] and not safe_retreat_activated and alive_enemies and self.hp > 0:
      hit_taken = random.randint(12, 25) * len(alive_enemies)
      if self.has_steel_hearts: hit_taken = int(hit_taken * 0.85)
      
      self.hp = max(0, self.hp - hit_taken)
      extra_info += f"\n\n⚠️ **HỎA LỰC PHẢN CÔNG TỪ {len(alive_enemies)} KẺ ĐỊCH:** Gây **-{hit_taken}% HP**!"
      extra_info += self.apply_random_crew_casualty()

    self.check_weather_cycle()

    if all(e["hp"] <= 0 for e in self.enemies):
      result_title = "🎉 CHIẾN THẮNG TRẬN ĐẤU"
      extra_info += "\n🏆 Chỉ huy Nam đã tiêu diệt sạch lực lượng thiết giáp địch!"

    prompt = f"Sĩ quan pháo thủ Yuri báo cáo lệnh '{action_desc}'. Kết quả: {extra_info}. Nhận xét ngắn gọn."
    report = "FCS cập nhật dữ liệu thành công."

    if ai_client:
      try:
        response = ai_client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt,
            config=types.GenerateContentConfig(system_instruction=YURI_MILITARY_SYSTEM_PROMPT),
        )
        if response and response.text: report = response.text.strip()
      except Exception:
        pass

    screen_art = generate_fcs_view(
        self.tank_name, self.fcs_type, self.speed, self.ammo, self.hp,
        self.enemies, self.active_target_idx, self.current_mission, self.enemy_status_text,
        self.repair_cooldown, self.aim_zeroing, self.current_weather["name"],
        self.action_counter, self.crew, self.has_lrf, self.get_defense_string(self.tank_name),
        self.has_steel_hearts, self.has_freedom_forever, self.retreat_charges
    )

    embed_color = discord.Color.green() if all(e["hp"] <= 0 for e in self.enemies) else (discord.Color.red() if self.hp <= 0 else discord.Color.dark_purple())

    embed = discord.Embed(
        title=result_title,
        description=f"> 🗡️ *\"{report}\"*\n\n```text\n{screen_art}\n```",
        color=embed_color,
    )
    
    if all(e["hp"] <= 0 for e in self.enemies) or self.hp <= 0:
      self.clear_items()

    await interaction.edit_original_response(embed=embed, view=self)

  # --- CÁC NÚT ĐIỀU KHIỂN GIAO DIỆN ---
  @discord.ui.button(label="🔄 Đổi mục tiêu", style=discord.ButtonStyle.blurple, row=0)
  async def btn_cycle(self, interaction: discord.Interaction, button: discord.ui.Button):
    await self.execute_action(interaction, "cycle_target", "Chuyển ngắm mục tiêu khác")

  @discord.ui.button(label="🎯 Khai hoả", style=discord.ButtonStyle.danger, row=0)
  async def btn_fire(self, interaction: discord.Interaction, button: discord.ui.Button):
    await self.execute_action(interaction, "fire", "Bắn pháo chính")

  @discord.ui.button(label="🚀 ATGM", style=discord.ButtonStyle.danger, row=0)
  async def btn_atgm(self, interaction: discord.Interaction, button: discord.ui.Button):
    await self.execute_action(interaction, "atgm", "Bắn tên lửa ATGM")

  @discord.ui.button(label="📏 Đo cự ly", style=discord.ButtonStyle.primary, row=0)
  async def btn_rf(self, interaction: discord.Interaction, button: discord.ui.Button):
    await self.execute_action(interaction, "rangefinder", "Sử dụng máy đo cự ly")

  @discord.ui.button(label="🔼 Nâng (+100m)", style=discord.ButtonStyle.secondary, row=1)
  async def btn_zero_up(self, interaction: discord.Interaction, button: discord.ui.Button):
    await self.execute_action(interaction, "zero_up", "Tăng thước ngắm +100m")

  @discord.ui.button(label="🔽 Hạ (-100m)", style=discord.ButtonStyle.secondary, row=1)
  async def btn_zero_down(self, interaction: discord.Interaction, button: discord.ui.Button):
    await self.execute_action(interaction, "zero_down", "Giảm thước ngắm -100m")

  @discord.ui.button(label="🛠️ Sửa chữa", style=discord.ButtonStyle.secondary, row=2)
  async def btn_repair(self, interaction: discord.Interaction, button: discord.ui.Button):
    await self.execute_action(interaction, "repair", "Khắc phục sự cố dã chiến")

  @discord.ui.button(label="🏕️ Nghỉ ngơi", style=discord.ButtonStyle.success, row=2)
  async def btn_rest(self, interaction: discord.Interaction, button: discord.ui.Button):
    await self.execute_action(interaction, "rest", "Nghỉ ngơi bổ sung kíp xe")

  @discord.ui.button(label="🚀 Tiến lên", style=discord.ButtonStyle.success, row=2)
  async def btn_forward(self, interaction: discord.Interaction, button: discord.ui.Button):
    await self.execute_action(interaction, "move_forward", "Cơ động tiến lên")

  @discord.ui.button(label="🔙 Lùi về", style=discord.ButtonStyle.secondary, row=2)
  async def btn_backward(self, interaction: discord.Interaction, button: discord.ui.Button):
    await self.execute_action(interaction, "move_backward", "Cơ động lùi về")


# ================= 5. HỆ THỐNG CÁC LỆNH TẦNG TRÊN (FULL COMMANDS) =================

@bot.event
async def on_message(message):
  if message.author == bot.user:
    return

  if bot.user.mentioned_in(message) and not message.content.startswith("!"):
    user_query = message.content.replace(f"<@!{bot.user.id}>", "").replace(f"<@{bot.user.id}>", "").strip()
    if not user_query: user_query = "Yuri đang báo cáo tình hình chiến trường."

    prompt = f"Chỉ huy Nam hỏi: '{user_query}'. Hãy trả lời cực kỳ ngắn gọn, sắc bén theo đúng phong cách Yuri."

    async with message.channel.typing():
      reply_text = "Dữ liệu tham mưu đang xử lý..."
      if ai_client:
        try:
          response = ai_client.models.generate_content(
              model='gemini-2.0-flash',
              contents=prompt,
              config=types.GenerateContentConfig(system_instruction=YURI_MILITARY_SYSTEM_PROMPT),
          )
          if response and response.text: reply_text = response.text.strip()
        except Exception:
          pass

    await message.reply(f"🗡️ *\"{reply_text}\"*\n- - -\n*Sĩ quan tham mưu Yuri*")
    return

  await bot.process_commands(message)

# Lệnh trợ giúp đầy đủ
@bot.command(name="Yhelps")
async def y_helps(ctx):
  embed = discord.Embed(
      title="📜 SỔ TAY TÁC CHIẾN & LỆNH BÀN GIAO MẶT TRẬN",
      description=(
          "🔹 **!campaign** - Mở bản đồ chiến dịch Đông Âu\n"
          "🔹 **!Yteam [Nga/Uka]** - Lựa chọn biên chế lực lượng\n"
          "🔹 **!deploy [tên xe]** - Triển khai khí tài vào trận địa\n"
          "🔹 **!fcs** - Bật màn hình FCS **Đa Mục Tiêu** (Đổi & bắn nhiều địch)\n"
          "🔹 **!Yprofile** - Xem hồ sơ sĩ quan chỉ huy\n"
          "🔹 **!Ysleep** - Cho kíp xe đi ngủ hồi phục thể lực\n"
          "🔹 **!Yguess [số]** - Minigame pháo thủ: Bắn thử đo cự ly"
      ),
      color=discord.Color.dark_red(),
  )
  await ctx.send(embed=embed)

# Lệnh xem Profile
@bot.command(name="Yprofile")
async def y_profile(ctx):
  user_id = ctx.author.id
  if user_id not in user_profiles:
    user_profiles[user_id] = {"rank": "Thiếu úy Thiết giáp", "battles": 1, "victories": 0}

  prof = user_profiles[user_id]
  embed = discord.Embed(
      title=f"🎖️ HỒ SƠ SĨ QUAN: {ctx.author.display_name}",
      description=(
          f"🔸 **Cấp bậc:** {prof['rank']}\n"
          f"🔸 **Số trận tham chiến:** {prof['battles']}\n"
          f"🔸 **Chiến thắng:** {prof['victories']}"
      ),
      color=discord.Color.gold()
  )
  await ctx.send(embed=embed)

# Lệnh nghỉ ngơi / ngủ qua đêm
@bot.command(name="Ysleep")
async def y_sleep(ctx):
  embed = discord.Embed(
      title="🌙 DỪNG TRẠI DÃ CHIẾN",
      description="Yuri: '*Toàn đội tiến vào trạng thái nghỉ ngơi đêm. Kíp xe đã hồi phục đầy đủ thể lực cho trận đánh tới.*'",
      color=discord.Color.blue()
  )
  await ctx.send(embed=embed)

# Minigame pháo thủ
@bot.command(name="Yguess")
async def y_guess(ctx, guess: int = None):
  guild_id = ctx.guild.id
  if guess is None:
    target_distance = random.randint(10, 100)
    active_guesses[guild_id] = target_distance
    embed = discord.Embed(title="🎯 MINIGAME PHÁO THỦ", description="Yuri: '*Phát hiện bia bắn ngẫu nhiên (1-100m)! Gõ `!Yguess [số]` để thử sức.*'", color=discord.Color.blue())
    return await ctx.send(embed=embed)

  if guild_id not in active_guesses:
    active_guesses[guild_id] = random.randint(10, 100)

  target = active_guesses[guild_id]

  if guess == target:
    del active_guesses[guild_id]
    embed = discord.Embed(title="💥 BẮN TRÚNG ĐÍCH!", description=f"Yuri mỉm cười: '*Cự ly chính xác tuyệt đối **{target}m**! Bắn hay lắm.*'", color=discord.Color.green())
  elif guess < target:
    embed = discord.Embed(title="📉 ĐẠN RƠI THẤP", description=f"Yuri: '*Nâng góc bắn lên cao hơn cự ly **{guess}m**!*'", color=discord.Color.orange())
  else:
    embed = discord.Embed(title="📈 ĐẠN BAY QUÁ CỰ LY", description=f"Yuri: '*Hạ góc bắn xuống thấp hơn cự ly **{guess}m**!*'", color=discord.Color.orange())

  await ctx.send(embed=embed)

# Quản lý Campaign & Team
@bot.command(name="campaign")
async def campaign(ctx):
  guild_id = ctx.guild.id
  game_sessions[guild_id] = {"team": None, "tanks": []}
  embed = discord.Embed(title="🌐 BẢN ĐỒ CHIẾN DỊCH TÁC CHIẾN", description="Yuri: '*Chỉ huy hãy chọn phe tác chiến: **`!Yteam Nga`** hoặc **`!Yteam Uka`**.*'", color=discord.Color.red())
  await ctx.send(embed=embed)

@bot.command(name="Yteam")
async def y_team(ctx, team_name: str):
  guild_id = ctx.guild.id
  team_lower = team_name.capitalize()
  if team_lower not in ["Nga", "Uka"]:
    return await ctx.send("⚠️ Phe không hợp lệ! Vui lòng chọn: `!Yteam Nga` hoặc `!Yteam Uka`.")

  if guild_id not in game_sessions: game_sessions[guild_id] = {"tanks": []}
  game_sessions[guild_id]["team"] = team_lower
  tanks = ", ".join([f"`{t}`" for t in TEAM_TANKS[team_lower]])

  embed = discord.Embed(
      title=f"🎖️ BÀN GIAO LỰC LƯỢNG: {team_lower.upper()}",
      description=f"Danh mục khí tài khả dụng: {tanks}\n\nGõ `!deploy [tên xe]` để xuất kích!",
      color=discord.Color.blue()
  )
  await ctx.send(embed=embed)

@bot.command(name="deploy")
async def deploy(ctx, tank_model: str, sector: str = "Tuyến đầu"):
  guild_id = ctx.guild.id
  if guild_id not in game_sessions or not game_sessions[guild_id].get("team"):
    return await ctx.send("⚠️ Chưa chọn phe! Vui lòng chọn `!campaign` rồi gõ `!Yteam`.")

  current_team = game_sessions[guild_id]["team"]
  if tank_model.lower() not in TEAM_TANKS[current_team]:
    return await ctx.send(f"❌ Khí tài `{tank_model}` không có trong biên chế lực lượng {current_team}!")

  game_sessions[guild_id]["tanks"].append({"model": tank_model.lower(), "sector": sector})
  await ctx.send(f"🛡️ Triển khai thành công **{tank_model.upper()}** tại {sector}! Gõ `!fcs` để vào giao diện tác chiến.")

@bot.command(name="fcs")
async def fcs(ctx):
  guild_id = ctx.guild.id
  tank_model = "bmpt"
  team_name = "Nga"
  
  if guild_id in game_sessions and game_sessions[guild_id].get("team"):
    team_name = game_sessions[guild_id]["team"]
  if guild_id in game_sessions and game_sessions[guild_id]["tanks"]:
    tank_model = game_sessions[guild_id]["tanks"][-1]["model"]

  fcs_mode = "basic" if any(x in tank_model.lower() for x in ["bmp-2", "bradley", "puma"]) else "t72"
  view = QuickChatFCSView(ctx, tank_model, team_name)
  
  initial_screen = generate_fcs_view(
      tank_model, fcs_mode, speed="Đứng yên", ammo=view.ammo, hp=100,
      enemies=view.enemies, active_target_idx=view.active_target_idx,
      mission="Tiêu diệt toàn bộ lực lượng địch", weather=view.current_weather["name"],
      action_counter=view.action_counter, crew_status=view.crew, has_lrf=view.has_lrf,
      defenses_info=view.get_defense_string(tank_model), has_steel_hearts=view.has_steel_hearts,
      has_freedom_forever=view.has_freedom_forever, retreat_charges=view.retreat_charges
  )
  
  embed = discord.Embed(
      title="🔭 HỆ THỐNG TÁC CHIẾN ĐA MỤC TIÊU (MULTI-TARGET FCS)",
      description=f"Yuri: '*Đã kích hoạt FCS! Phát hiện nhiều mục tiêu thiết giáp địch xuất hiện trên màn hình radar.*'\n```text\n{initial_screen}\n```",
      color=discord.Color.dark_purple(),
  )
  await ctx.send(embed=embed, view=view)

# ================= 6. KHỞI CHẠY BOT =================
@bot.event
async def on_ready():
  print(f"✅ Bot Yuri War Thunder (Full Engine & Multi-Target) đã online: {bot.user.name}")

if __name__ == "__main__":
  keep_alive()
  if DISCORD_TOKEN:
    bot.run(DISCORD_TOKEN)
  else:
    print("❌ LỖI: Chưa cài đặt DISCORD_TOKEN trong Environment Variable!")
