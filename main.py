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
  return "War Thunder Dynamic Night/Storm & FCS System is operational..."


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

# Yuri giữ phong cách cực kỳ ngắn gọn, nói dài hơn một chút khi ở FCS
YURI_MILITARY_SYSTEM_PROMPT = (
    "Bạn là Yuri - Sĩ quan tham mưu kiêm pháo thủ thiết giáp. Tính cách sắc"
    " sảo, am hiểu chiến thuật. Nói cực kỳ ngắn gọn (dưới 3 câu), trừ khi ở"
    " giao diện FCS thì có thể dài hơn một chút để phân tích thông số kỹ"
    " thuật."
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
    self.action_counter = 0  # Đếm số lần hành động để kích hoạt chu kỳ thời tiết

  def check_weather_cycle(self):
    """Sau mỗi khoảng 4 lần tin nhắn, có 75% tỉ lệ thời tiết đêm/bão kết thúc để trở lại ban ngày."""
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

    # Kiểm tra thời tiết khắc nghiệt
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
          "⏳ *Yuri lúng túng ôm bảng mạch: 'Vui lòng đợi 1 phút game đang sắp"
          " xếp...'*"
      )
      await asyncio.sleep(1.5)
      try:
        await temp_msg.delete()
      except Exception:
        pass

      extra_info = (
          f"🛠️ Đang sửa chữa dã chiến... (Còn lại {self.repair_cooldown} lượt"
          " đóng băng)."
      )
      result_title = "⚙️ BẢO TRÌ CHIẾN TRƯỜNG"

      hit_taken = random.randint(15, 45)
      self.hp = max(0, self.hp - hit_taken)
      extra_info += f"\n⚠️ **Địch chớp thời cơ nã pháo:** Gây -{hit_taken}% HP!"

      if self.hp <= 0:
        self.current_mission = "Đã bị bắn hạ (Wrecked)"
        result_title = "❌ CHIẾN TRƯỜNG KẾT THÚC"

      # Kiểm tra chu kỳ 4 lần tin nhắn
      weather_cleared = self.check_weather_cycle()
      if weather_cleared:
        extra_info += "\n⛅ **Bầu trời chuyển biến:** Bão tố/Đêm tối đã chấm dứt, trời quang mây tạnh!"

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
          description=f"*Yuri mồ hôi đầm đìa: 'Cố lên, xe chịu đựng chút nữa!'*\n\n```text\n{screen_art}\n```",
          color=discord.Color.red() if self.hp <= 0 else discord.Color.orange(),
      )
      return await interaction.message.edit(embed=embed, view=self)

    # Tin nhắn chờ xử lý, tự động xóa sau 4 giây
    await interaction.response.defer()
    temp_msg = await interaction.followup.send(
        "⏳ *Yuri vội vàng chỉnh lại gọng kính: 'Vui lòng đợi 1 phút game đang sắp"
        " xếp...'*"
    )

    async def delete_temp_msg():
      await asyncio.sleep(4)
      try:
        await temp_msg.delete()
      except Exception:
        pass

    asyncio.create_task(delete_temp_msg())

    extra_info = ""
    result_title = ""
    enemy_dmg = 0

    if action_type == "rest":
      # Dùng lệnh ngủ/nghỉ ngơi: Tăng tỉ lệ địch phục kích từ 25% lên 45%
      ambush_chance = 45
      hit_by_enemy_first = random.randint(1, 100) <= ambush_chance
      if hit_by_enemy_first:
        enemy_surprise_dmg = random.randint(15, 45)
        self.hp = max(0, self.hp - enemy_surprise_dmg)
        extra_info = (
            f"⚠️ **Địch phục kích khi đang ngủ!** (Tỉ lệ {ambush_chance}%) Trúng đòn mất"
            f" -{enemy_surprise_dmg}% HP trước khi kịp tỉnh giấc."
        )
      else:
        extra_info = (
            "🛡️ Cắm trại an toàn. Yuri pha trà nóng động"
            " viên!"
        )

      heal_amount = random.randint(20, 40)
      self.hp = min(100, self.hp + heal_amount)
      extra_info += (
          f"\n🏕️ Nghỉ ngơi thành công: Hồi phục **+{heal_amount}% HP**!"
      )
      result_title = "🏕️ NGHỈ NGƠI & TÁI TẠO LỰC LƯỢNG"
      self.current_mission = "Phòng thủ & Hồi sức"
      self.current_weather = random.choice(WEATHER_CONDITIONS)

    elif action_type == "fire":
      hit_chance = 85 if self.fcs_type == "t72" else 60
      if "Sương mù" in self.current_weather["name"]:
        hit_chance -= 20

      is_hit = random.randint(1, 100) <= hit_chance

      if not is_hit:
        result_title = "🎯 KHAI HỎA: MISS / BẮN TRƯỢT"
        extra_info = "Đường đạn bị ảnh hưởng bởi tầm nhìn và khoảng cách!"
      else:
        wt_type = random.choice(["NON-PEN", "HIT", "CRITICAL"])
        if wt_type == "NON-PEN":
          enemy_dmg = random.randint(0, 5)
          result_title = "🎯 KHAI HỎA: NON-PEN (Bật giáp)"
          extra_info = (
              f"Đạn va chạm nhưng không xuyên được giáp địch! Gây -{enemy_dmg}%"
              " HP."
          )
        elif wt_type == "HIT":
          enemy_dmg = random.randint(15, 45)
          result_title = "🎯 KHAI HỎA: XUYÊN THỦNG (HIT)"
          extra_info = (
              f"Viên đạn xé gió xuyên thẳng vào khoang chiến đấu! Gây"
              f" -{enemy_dmg}% HP."
          )
        else:
          enemy_dmg = random.randint(25, 50)
          result_title = "🎯 KHAI HỎA: CRITICAL HIT"
          extra_info = (
              f"Trúng điểm yếu chí mạng của địch, phá hủy hệ thống! Gây"
              f" -{enemy_dmg}% HP."
          )

    elif action_type == "binocular":
      self.locked_distance = random.randint(400, 2800)
      num_enemies = random.randint(1, 3)
      enemy_lines = []
      for i in range(1, num_enemies + 1):
        e_hp = random.choice([40, 70, 100])
        e_bar = "█" * (e_hp // 20) + "░" * (5 - (e_hp // 20))
        e_name = random.choice(["T-72B3", "Leopard 2", "M1A1 Abrams", "BMP-2"])
        enemy_lines.append(
            f" địch #{i} [{e_name}] | HP: [{e_bar}] {e_hp}%"
        )

      result_title = "🔭 QUAN SÁT ỐNG NHÒM (TRINH SÁT)"
      self.enemy_status_text = "\n".join(enemy_lines)
      extra_info = f"Đã quét mục tiêu qua ống kính ở cự ly **{self.locked_distance}m**."
      self.current_mission = "Tiêu diệt kẻ địch"

    elif action_type == "move_forward":
      self.speed = "Tiến lên tuyến đầu"
      result_title = "🏎️ CƠ ĐỘNG: TIẾN LÊN"
      extra_info = "Tăng tốc vượt chướng ngại vật, tạo góc khai hỏa mới."
      self.current_mission = "Tiên phong đột phá"

    elif action_type == "move_backward":
      self.speed = "Lùi về ẩn nấp"
      result_title = "🔙 CƠ ĐỘNG: LÙI VỀ"
      extra_info = "Rút lui về sau gờ đất né làn đạn."
      self.current_mission = "Trinh sát chiến tuyến"

    elif action_type == "repair":
      self.repair_cooldown = 2
      self.speed = "Đang đứng sửa chữa dã chiến"
      result_title = "🛠️ SỬA CHỮA DÃ CHIẾN"
      heal_amount = random.randint(20, 40)
      self.hp = min(100, self.hp + heal_amount)
      extra_info = (
          f"Hàn gắn khung gầm, hồi phục **+{heal_amount}% HP**! (Mất 2 lượt"
          " hành động kế tiếp)"
      )
      self.current_mission = "Sửa chữa & Phòng thủ"

    # Kiểm tra chu kỳ thời tiết sau hành động
    weather_cleared = self.check_weather_cycle()
    if weather_cleared:
      extra_info += "\n⛅ **Bầu trời chuyển biến:** Bão tố/Đêm tối đã chấm dứt, trời quang mây tạnh!"

    # Địch phản công thông thường
    if (
        action_type not in ["move_backward", "repair", "rest"]
        and enemy_dmg < 100
        and self.hp > 0
    ):
      hit_taken = random.randint(15, 45)
      self.hp = max(0, self.hp - hit_taken)
      extra_info += f"\n⚠️ **Địch phản công:** Gây -{hit_taken}% HP!"

    if self.hp <= 0:
      self.current_mission = "Đã bị bắn hạ (Wrecked)"
      result_title = "❌ CHIẾN TRƯỜNG KẾT THÚC"

    # Gọi Gemini phản hồi tâm trạng Yuri (ngắn gọn, phân tích thông số khi ở FCS)
    prompt = (
        f"Sĩ quan thực hiện '{action_desc}' trong thời tiết"
        f" {self.current_weather['name']}. {extra_info}. Nhiệm vụ hiện tại:"
        f" {self.current_mission}. Hãy phân tích thông số kỹ thuật ngắn gọn qua giao diện FCS."
    )
    report = "Hệ thống FCS hoạt động ổn định."

    models_to_try = ["gemini-3.6-flash", "gemini-2.5-flash"]
    for m in models_to_try:
      try:
        response = ai_client.models.generate_content(
            model=m,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=YURI_MILITARY_SYSTEM_PROMPT
            ),
        )
        if response and response.text:
          report = response.text
          break
      except Exception:
        continue

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
        description=f"*{report}*\n\n```text\n{screen_art}\n```",
        color=discord.Color.red() if self.hp <= 0 else discord.Color.dark_red(),
    )
    embed.add_field(name="🛡️ Khí tài", value=self.tank_name, inline=True)
    embed.add_field(name="❤️ HP", value=f"{self.hp}%", inline=True)
    embed.add_field(name="🌦️ Thời tiết", value=self.current_weather["name"], inline=True)
    
    if self.hp <= 0:
      self.clear_items()
      
    await interaction.message.edit(embed=embed, view=self)

  @discord.ui.button(label="🎯 Khai hoả", style=discord.ButtonStyle.danger)
  async def btn_fire(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await self.execute_action(interaction, "fire", "Khai hỏa tiêu diệt địch")

  @discord.ui.button(label="🔭 Quan sát", style=discord.ButtonStyle.primary)
  async def btn_binocular(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await self.execute_action(
        interaction, "binocular", "Sử dụng ống nhòm trinh sát"
    )

  @discord.ui.button(label="🛠️ Sửa chữa", style=discord.ButtonStyle.secondary)
  async def btn_repair(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await self.execute_action(
        interaction, "repair", "Tiến hành sửa chữa dã chiến"
    )

  @discord.ui.button(label="🏕️ Nghỉ ngơi", style=discord.ButtonStyle.success)
  async def btn_rest(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await self.execute_action(
        interaction, "rest", "Nghỉ ngơi, cắm trại và trò chuyện với Yuri"
    )

  @discord.ui.button(label="🚀 Tiến lên", style=discord.ButtonStyle.success)
  async def btn_forward(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await self.execute_action(interaction, "move_forward", "Tiến lên tuyến đầu")

  @discord.ui.button(label="🔙 Lùi về", style=discord.ButtonStyle.secondary)
  async def btn_backward(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await self.execute_action(
        interaction, "move_backward", "Lùi về vị trí an toàn"
    )


# ================= 4. CÁC LỆNH BOT =================
@bot.command(name="Yhelps")
async def y_helps(ctx):
  embed = discord.Embed(
      title="📜 SỔ TAY CHIẾN DỊCH (DYNAMIC)",
      description=(
          "1. `!campaign` - Mở bản đồ\n2. `!Yteam [Nga/Uka]` - Chọn phe\n3."
          " `!deploy [tên xe]` - Xuất chiến\n4. `!fcs` - Mở giao diện tác chiến\n5."
          " `!Ysleep` - Đi ngủ / Nghỉ ngơi nhanh"
      ),
      color=discord.Color.dark_red(),
  )
  await ctx.send(embed=embed)


@bot.command(name="Ysleep")
async def y_sleep(ctx):
  """Lệnh chat đi ngủ nhanh ngoài chiến trường (tăng tỉ lệ địch phục kích 45%)"""
  guild_id = ctx.guild.id
  if guild_id not in game_sessions or not game_sessions[guild_id].get("tanks"):
    return await ctx.send("⚠️ Bạn chưa triển khai xe tăng nào ra chiến trường!")
  
  ambush_chance = 45
  hit_by_enemy = random.randint(1, 100) <= ambush_chance
  msg = f"🏕️ Nam lệnh cho kíp chiến đấu đi ngủ để hồi phục sức lực...\n"
  if hit_by_enemy:
    dmg = random.randint(15, 45)
    msg += f"⚠️ **Cảnh báo phục kích!** (Tỉ lệ {ambush_chance}%) Địch bất ngờ nã pháo gây -{dmg}% HP trong lúc chợp mắt!"
  else:
    msg += "🛡️ Giấc ngủ bình yên dưới chiến hào, kíp lái lấy lại toàn bộ tinh thần."

  embed = discord.Embed(
      title="💤 NGHỈ NGƠI CHIẾN TRƯỜNG (!YSLEEP)",
      description=msg,
      color=discord.Color.green() if not hit_by_enemy else discord.Color.orange(),
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
      {"model": tank_model, "sector": sector}
  )
  await ctx.send(
      f"🛡️ Triển khai thành công **{tank_model}** tại {sector}! Gõ `!fcs` để"
      " mở giao diện tác chiến."
  )


@bot.command(name="fcs")
async def fcs(ctx):
  guild_id = ctx.guild.id
  tank_model = "t-90a"
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
      ammo="APFSDS",
      hp=100,
      mission="Tiêu diệt địch",
      weather=view.current_weather["name"],
      action_counter=view.action_counter,
  )
  embed = discord.Embed(
      title="🔭 HỆ THỐNG FCS & CHU KỲ CHIẾN TRƯỜNG",
      description=(
          f"Yuri: '*Bắt đầu tác chiến với **{tank_model}**!*'\n```text\n"
          f"{initial_screen}\n```"
      ),
      color=discord.Color.dark_purple(),
  )
  await ctx.send(embed=embed, view=view)


@bot.event
async def on_ready():
  print(f"✅ Yuri Dynamic Cycle Bot đã sẵn sàng: {bot.user.name}")


if __name__ == "__main__":
  keep_alive()
  bot.run(DISCORD_TOKEN)
