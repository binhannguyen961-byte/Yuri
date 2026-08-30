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
  return "War Thunder Turn-Based Dual-FCS System is operational..."


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

YURI_MILITARY_SYSTEM_PROMPT = (
    "Bạn là Yuri - một nhân vật trong doki doki liturate club nhưng có role Sĩ quan tham mưu kiêm pháo thủ thiết giáp (kết hợp phong"
    " cách game turn-based và War Thunder). Tính cách: sắc sảo, am hiểu thông"
    " số kỹ thuật, thỉnh thoảng hơi ngượng ngùng khi bị trêu. Hãy viết cực kỳ"
    " ngắn gọn, sắc bén, dưới 3 câu."
)


# ================= 3. GIAO DIỆN HAI LOẠI FCS (BASIC & T-72BV STYLE) =================
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
):
  hp_bar = "█" * (hp // 20) + "░" * (5 - (hp // 20))

  if fcs_type == "basic":
    # Giao diện Basic: Giống tank đời cũ không có FCS, đo khoảng cách thủ công, thước ngắm quang học thô
    screen = f"""[OPTICS: {tank_name.upper()} - BASIC SIGHT] | HP: [{hp_bar}] {hp}%
⚙️ Cơ động: {speed} | 📦 Đạn: {ammo}
🎯 Mục tiêu: {mission}"""
    if cooldown_turns > 0:
      screen += f"\n⚠️ TRẠNG THÁI: Sửa chữa dã chiến (Còn {cooldown_turns} lượt)"
    if enemy_info:
      screen += f"\n-----------------------------------\n{enemy_info}"
    else:
      screen += (
          "\n-----------------------------------\n    |     (Thước ngắm"
          " quang học)\n  - | -   (Ước lượng cự ly thủ công)"
          f"\n    |     [Khoảng cách ~{locked_distance}m]"
      )
  else:
    # Giao diện T-72B3 / Hiện đại: Có máy tính đường đạn, LRF tự động khóa mục tiêu
    screen = f"""[FCS BẠN ĐỒNG HÀNH: {tank_name.upper()} - T-72BV/B3 LRF] | HP: [{hp_bar}] {hp}%
⚙️ Cơ động: {speed} | 📦 Đạn: {ammo}
🎯 Mục tiêu: {mission}"""
    if cooldown_turns > 0:
      screen += f"\n⚠️ TRẠNG THÁI: Sửa chữa dã chiến (Còn {cooldown_turns} lượt)"
    if enemy_info:
      screen += f"\n-----------------------------------\n{enemy_info}"
    else:
      screen += (
          "\n-----------------------------------\n   [ LOCKED: AUTO BALLISTIC"
          f" ] (Cự ly chuẩn {locked_distance}m)\n   /   [ + ]   \\"
      )

  return screen


class QuickChatFCSView(discord.ui.View):

  def __init__(self, ctx, tank_name):
    super().__init__(timeout=180)
    self.ctx = ctx
    self.tank_name = tank_name
    # Tự động nhận diện loại FCS dựa trên tên xe (T-72, T-90, T-80, Abrams, Leopard dùng loại T-72BV; xe đời đầu/nhẹ dùng Basic)
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

  async def execute_action(
      self, interaction: discord.Interaction, action_type, action_desc
  ):
    if interaction.user != self.ctx.author:
      return await interaction.response.send_message(
          "⚠️ Không có quyền can thiệp!", ephemeral=True
      )
    if self.hp <= 0:
      return await interaction.response.send_message(
          "❌ Xe đã bị phá hủy hoàn toàn! Hãy dùng lệnh triển khai lại.",
          ephemeral=True,
      )

    if self.repair_cooldown > 0:
      if action_type == "repair":
        return await interaction.response.send_message(
            "⚠️ Xe tăng đang trong quá trình sửa chữa rồi!", ephemeral=True
        )

      self.repair_cooldown -= 1
      await interaction.response.defer()

      temp_msg = await interaction.followup.send(
          "⏳ *Yuri lúng túng ôm bảng mạch: 'Vui lòng đợi 1 phút game đang sắp"
          " xếp...'*"
      )
      await asyncio.sleep(2)
      try:
        await temp_msg.delete()
      except Exception:
        pass

      extra_info = (
          f"🛠️ Đang sửa chữa dã chiến... (Còn lại {self.repair_cooldown} lượt"
          " đóng băng)."
      )
      result_title = "⚙️ BẢO TRÌ CHIẾN TRƯỜNG"

      hit_taken = random.choice([10, 20])
      self.hp = max(0, self.hp - hit_taken)
      extra_info += f"\n⚠️ **Địch chớp thời cơ nã pháo:** Gây -{hit_taken}% HP!"

      if self.hp <= 0:
        self.current_mission = "Đã bị bắn hạ (Wrecked)"

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
      )
      embed = discord.Embed(
          title=result_title,
          description=f"*Yuri mồ hôi đầm đìa: 'Cố lên, đừng hỏng lúc này!'*\n\n```text\n{screen_art}\n```",
          color=discord.Color.orange(),
      )
      embed.add_field(name="🛡️ Khí tài", value=self.tank_name, inline=True)
      embed.add_field(name="❤️ HP", value=f"{self.hp}%", inline=True)
      embed.add_field(name="📋 Nhiệm vụ", value=self.current_mission, inline=True)
      return await interaction.message.edit(embed=embed, view=self)

    # Nhắn thông báo chờ xử lý và tự động xóa sau 10 giây
    await interaction.response.defer()
    temp_msg = await interaction.followup.send(
        "⏳ *Yuri vội vàng chỉnh lại gọng kính: 'Vui lòng đợi 1 phút game đang sắp"
        " xếp...'*"
    )

    async def delete_temp_msg():
      await asyncio.sleep(10)
      try:
        await temp_msg.delete()
      except Exception:
        pass

    asyncio.create_task(delete_temp_msg())

    extra_info = ""
    result_title = ""
    enemy_dmg = 0

    if action_type == "fire":
      # Tỉ lệ trúng và xuyên phụ thuộc vào loại FCS (Loại T-72BV chuẩn xác hơn Basic)
      hit_chance = 85 if self.fcs_type == "t72" else 60
      is_hit = random.randint(1, 100) <= hit_chance

      if not is_hit:
        result_title = "🎯 KHAI HỎA: MISS / BẮN TRƯỢT"
        extra_info = (
            "Đạn bay chệch mục tiêu do không có máy tính đường đạn hỗ trợ tối"
            " ưu!"
            if self.fcs_type == "basic"
            else "Mục tiêu tạt sườn né được đường đạn!"
        )
      else:
        wt = random.choice([
            ("NON-PEN", "Đạn bật giáp đối phương!", 0),
            ("HIT", "Xuyên thủng khoang chiến đấu địch!", 25),
            ("CRITICAL", "Phá hủy hệ thống ngắm bắn của địch!", 50),
            ("TARGET DESTROYED", "Hạ gục mục tiêu hoàn toàn!", 100),
        ])
        result_title = f"🎯 KHAI HỎA: {wt[0]}"
        extra_info = f"Kết quả: {wt[1]}"
        enemy_dmg = wt[2]

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

      result_title = (
          "🔭 QUAN SÁT ỐNG NHÒM (LRF ĐO CỰ LY)"
          if self.fcs_type == "t72"
          else "🔭 QUAN SÁT ỐNG NHÒM (ĐO CỰ LY THỦ CÔNG)"
      )
      self.enemy_status_text = "\n".join(enemy_lines)
      extra_info = f"Đã khóa khoảng mục tiêu ở cự ly **{self.locked_distance}m** qua hệ thống quang học!"
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
      heal_amount = 30
      self.hp = min(100, self.hp + heal_amount)
      extra_info = (
          f"Hàn gắn khung gầm, hồi phục **+{heal_amount}% HP**! (Mất 2 lượt"
          " hành động kế tiếp)"
      )
      self.current_mission = "Sửa chữa & Phòng thủ"

    if action_type != "move_backward" and action_type != "repair" and enemy_dmg < 100:
      hit_taken = random.choice([0, 15, 30])
      self.hp = max(0, self.hp - hit_taken)
      if hit_taken > 0:
        extra_info += f"\n⚠️ **Địch phản công:** Gây -{hit_taken}% HP!"
      else:
        extra_info += "\n🛡️ **Địch phản công:** Bắn trượt trong gang tấc!"
    elif action_type == "repair":
      extra_info += "\n🛡️ Đội ngũ kỹ thuật đang tập trung sửa xe dưới làn đạn!"

    if self.hp <= 0:
      self.current_mission = "Đã bị bắn hạ (Wrecked)"

    # Gọi Gemini với cơ chế tự động chuyển model thông minh (3.6 -> 2.5)
    prompt = (
        f"Sĩ quan thực hiện '{action_desc}' với hệ thống ngắm {self.fcs_type}."
        f" {extra_info}. Nhiệm vụ hiện tại: {self.current_mission}. Viết báo"
        " cáo chiến sự ngắn gọn, sắc sảo đúng chất Yuri (dưới 3 câu)."
    )
    report = "Giao tranh diễn ra ác liệt trên chiến tuyến."

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
    )

    embed = discord.Embed(
        title=result_title,
        description=f"*{report}*\n\n```text\n{screen_art}\n```",
        color=discord.Color.dark_red(),
    )
    embed.add_field(name="🛡️ Khí tài", value=self.tank_name, inline=True)
    embed.add_field(
        name="🔧 Hệ thống ngắm",
        value=self.fcs_type.upper(),
        inline=True,
    )
    embed.add_field(name="❤️ HP", value=f"{self.hp}%", inline=True)
    await interaction.message.edit(embed=embed, view=self)

  @discord.ui.button(label="🎯 Khai hoả", style=discord.ButtonStyle.danger)
  async def btn_fire(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await self.execute_action(interaction, "fire", "Khai hỏa tiêu diệt địch")

  @discord.ui.button(label="🔭 Quan sát ống nhòm", style=discord.ButtonStyle.primary)
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
      title="📜 SỔ TAY CHIẾN DỊCH (DUAL FCS)",
      description=(
          "1. `!campaign` - Mở bản đồ\n2. `!Yteam [Nga/Uka]` - Chọn phe\n3."
          " `!deploy [tên xe]` - Xuất chiến\n4. `!fcs` - Mở giao diện ngắm bắn"
          " (Tự động chọn loại Basic hoặc T-72BV tùy xe)"
      ),
      color=discord.Color.dark_red(),
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
  fcs_preview = (
      "Basic Optics"
      if any(x in tank_model.lower() for x in ["bmp-2", "bradley", "puma"])
      else "T-72BV FCS"
  )
  await ctx.send(
      f"🛡️ Triển khai thành công **{tank_model}** ({fcs_preview}) tại"
      f" {sector}! Gõ `!fcs` để mở giao diện tác chiến."
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
  initial_screen = generate_fcs_view(
      tank_model,
      fcs_mode,
      speed="Đứng yên",
      ammo="APFSDS",
      hp=100,
      mission="Tiêu diệt địch",
  )
  embed = discord.Embed(
      title=f"🔭 HỆ THỐNG FCS: {fcs_mode.upper()}",
      description=(
          f"Yuri: '*Bắt đầu tác chiến với **{tank_model}**!*'\n```text\n"
          f"{initial_screen}\n```"
      ),
      color=discord.Color.dark_purple(),
  )
  view = QuickChatFCSView(ctx, tank_model)
  await ctx.send(embed=embed, view=view)


@bot.event
async def on_ready():
  print(f"✅ Yuri Dual-FCS Bot đã sẵn sàng: {bot.user.name}")


if __name__ == "__main__":
  keep_alive()
  bot.run(DISCORD_TOKEN)
