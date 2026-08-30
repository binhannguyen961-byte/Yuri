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
  return "War Thunder Turn-Based FCS Command Center is operational..."


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
    "Bạn là Yuri - Sĩ quan tham mưu kiêm pháo thủ thiết giáp (kết hợp phong"
    " cách game turn-based và War Thunder). Tính cách: sắc sảo, am hiểu thông"
    " số kỹ thuật, thỉnh thoảng hơi ngượng ngùng. Hãy viết cực kỳ ngắn gọn, sắc"
    " bén, dưới 3 câu."
)


# ================= 3. GIAO DIỆN KÍNH NGẮM FCS & TURN-BASED =================
def generate_fcs_view(
    tank_name,
    speed="Đứng yên",
    ammo="APFSDS",
    hp=100,
    mission="Tiêu diệt địch",
    enemy_info="",
):
  hp_bar = "█" * (hp // 20) + "░" * (5 - (hp // 20))
  screen = f"""[FCS: {tank_name.upper()}] | HP: [{hp_bar}] {hp}%
⚙️ Cơ động: {speed} | 📦 Đạn: {ammo}
🎯 Mục tiêu: {mission}"""
  if enemy_info:
    screen += f"\n-----------------------------------\n{enemy_info}"
  else:
    screen += "\n-----------------------------------\n      [ - ] (Khóa mục tiêu 1650m)\n   /   |   \\"
  return screen


class QuickChatFCSView(discord.ui.View):

  def __init__(self, ctx, tank_name):
    super().__init__(timeout=180)
    self.ctx = ctx
    self.tank_name = tank_name
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

  async def execute_action(
      self, interaction: discord.Interaction, action_type, action_desc
  ):
    if interaction.user != self.ctx.author:
      return await interaction.response.send_message(
          "⚠️ Không có quyền can thiệp!", ephemeral=True
      )
    if self.hp <= 0:
      return await interaction.response.send_message(
          "❌ Xe đã bị phá hủy! Hãy dùng lệnh sửa chữa.", ephemeral=True
      )

    await interaction.response.defer()

    extra_info = ""
    result_title = ""
    enemy_dmg = 0

    if action_type == "fire":
      wt = random.choice([
          ("NON-PEN", "Đạn bật giáp địch!", 0),
          ("HIT", "Xuyên thủng gây tổn thất khoang chiến đấu!", 20),
          ("CRITICAL", "Phá hủy bộ phận quan trọng của địch!", 40),
          ("TARGET DESTROYED", "Tiêu diệt gọn mục tiêu!", 80),
      ])
      result_title = f"🎯 KHAI HỎA: {wt[0]}"
      extra_info = f"Kết quả: {wt[1]}"
      enemy_dmg = wt[2]

    elif action_type == "binocular":
      # Cơ chế Turn-base RPG: Phát hiện nhiều kẻ địch kèm thanh máu
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
      extra_info = f"Phát hiện **{num_enemies} mục tiêu** trên chiến trường!"
      self.current_mission = "Tiêu diệt kẻ địch"

    elif action_type == "move_forward":
      self.speed = "Tiến lên tuyến đầu"
      result_title = "🏎️ CƠ ĐỘNG: TIẾN LÊN"
      extra_info = "Tăng tốc vượt chướng ngại vật, tạo góc bắn mới."
      self.current_mission = "Tiên phong đột phá"

    elif action_type == "move_backward":
      self.speed = "Lùi về ẩn nấp"
      result_title = "🔙 CƠ ĐỘNG: LÙI VỀ"
      extra_info = "Rút lui về sau gờ đất né làn đạn."
      self.current_mission = "Trinh sát chiến tuyến"

    if action_type != "move_backward" and enemy_dmg < 80:
      hit_taken = random.choice([0, 15, 30])
      self.hp = max(0, self.hp - hit_taken)
      if hit_taken > 0:
        extra_info += f"\n⚠️ **Địch phản công:** Gây -{hit_taken}% HP!"
      else:
        extra_info += "\n🛡️ **Địch phản công:** Bắn trượt!"
    else:
      extra_info += "\n✨ Mục tiêu đã tê liệt."

    if self.hp <= 0:
      self.current_mission = "Đã bị bắn hạ (Wrecked)"

    # Gọi Gemini với cơ chế tự động chuyển model nếu quá tải (3.6 -> 2.5)
    prompt = (
        f"Sĩ quan thực hiện '{action_desc}'. {extra_info}. Nhiệm vụ hiện tại:"
        f" {self.current_mission}. Viết báo cáo chiến sự ngắn gọn, sắc sảo"
        " đúng chất Yuri (dưới 3 câu)."
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
        self.speed,
        self.ammo,
        self.hp,
        self.current_mission,
        self.enemy_status_text,
    )

    embed = discord.Embed(
        title=result_title,
        description=f"*{report}*\n\n```text\n{screen_art}\n```",
        color=discord.Color.dark_red(),
    )
    embed.add_field(name="🛡️ Khí tài", value=self.tank_name, inline=True)
    embed.add_field(name="❤️ HP", value=f"{self.hp}%", inline=True)
    embed.add_field(name="📋 Nhiệm vụ", value=self.current_mission, inline=True)
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
      title="📜 SỔ TAY CHIẾN DỊCH",
      description=(
          "1. `!campaign` - Mở bản đồ\n2. `!Yteam [Nga/Uka]` - Chọn phe\n3."
          " `!deploy [tên xe]` - Xuất chiến\n4. `!fcs` - Mở giao diện chiến đấu"
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
          "Yuri đẩy gọng kính: '*Đồng chí đã sẵn sàng chưa? Hãy chọn phe bằng lệnh"
          " **`!Yteam Nga`** hoặc **`!Yteam Uka`** nhé!*'"
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
      " chiến đấu."
  )


@bot.command(name="fcs")
async def fcs(ctx):
  guild_id = ctx.guild.id
  tank_model = "t-90a"
  if guild_id in game_sessions and game_sessions[guild_id]["tanks"]:
    tank_model = game_sessions[guild_id]["tanks"][-1]["model"]

  initial_screen = generate_fcs_view(
      tank_model,
      speed="Đứng yên",
      ammo="APFSDS",
      hp=100,
      mission="Tiêu diệt kẻ địch",
  )
  embed = discord.Embed(
      title="🔭 KÍNH NGẮM FCS & TURN-BASED",
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
  print(f"✅ Yuri Bot Turn-Based Mode đã sẵn sàng: {bot.user.name}")


if __name__ == "__main__":
  keep_alive()
  bot.run(DISCORD_TOKEN)
