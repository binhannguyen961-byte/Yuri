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


# ================= 2. CẤU HÌNH BOT & GEMINI (YURI - TURN BASED) =================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "YOUR_DISCORD_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY")

ai_client = genai.Client(api_key=GEMINI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# Lưu trữ trạng thái chiến dịch và phe phái của người chơi
game_sessions = {}

# Danh sách kho xe tăng theo phe (Chuẩn hóa chữ thường để dễ đối chiếu)
TEAM_TANKS = {
    "Nga": ["t-80", "t-90a", "bmp-3", "bmpt", "t-90m", "t-72b3m", "t-64bv"],
    "Uka": ["m1a1-abrams", "leopard-2a7", "bradley-tusk", "puma", "bmp-2", "t-72b3"],
}

YURI_MILITARY_SYSTEM_PROMPT = (
    "Bạn là Yuri - nhân vật từ câu lạc bộ văn học (DDLC) kiêm Nữ Sĩ quan Tham"
    " mưu / Pháo thủ thiết giáp cao cấp. Tính cách: sắc sảo, am hiểu thông số"
    " kỹ thuật xe tăng, nhưng thỉnh thoảng vẫn lấp ló nét rụt rè, mẫn cảm và"
    " hơi ngượng ngùng khi trò chuyện với đồng chí sĩ quan."
)


# ================= 3. GIAO DIỆN KÍNH NGẮM FCS & TURN-BASED COMBAT =================
def generate_fcs_view(
    tank_name,
    turret_dir="12 giờ",
    speed="Đứng yên",
    ammo="APFSDS",
    hp=100,
    status="Bình thường",
):
  hp_bar = "█" * (hp // 10) + "░" * (10 - (hp // 10))
  fcs_screen = f"""
┌──────────────────────────────────────────────┐
│ [WAR THUNDER FCS] - KHÍ TÀI: {tank_name.upper()}   │
├──────────────────────────────────────────────┤
│       [ - ]  <- Khóa mục tiêu laser          │
│    \\          |          /                   │
│     \\     [+1650m]      /                    │
│  ─────── O ───────────────                   │
│     /       |       \\                        │
│    /        |        \\                       │
├──────────────────────────────────────────────┤
│ 🎯 Hướng tháp pháo: [{turret_dir}]             │
│ ⚙️ Cơ động: [{speed}] | 📦 Đạn: [{ammo}]       │
│ ❤️ Độ bền xe: [{hp_bar}] {hp}% ({status})      │
└──────────────────────────────────────────────┘
"""
  return fcs_screen


class QuickChatFCSView(discord.ui.View):

  def __init__(self, ctx, tank_name):
    super().__init__(timeout=180)
    self.ctx = ctx
    self.tank_name = tank_name
    self.turret_dir = "12 giờ"
    self.speed = "Đứng yên ngắm bắn"
    self.ammo = "APFSDS"
    self.hp = 100
    self.status = "Sẵn sàng chiến đấu"

  async def process_fcs_action(
      self, interaction: discord.Interaction, action_desc
  ):
    if interaction.user != self.ctx.author:
      return await interaction.response.send_message(
          "⚠️ Cảnh cáo! Đồng chí không có quyền can thiệp vào hệ thống FCS này!",
          ephemeral=True,
      )

    if self.hp <= 0:
      return await interaction.response.send_message(
          "❌ Xe tăng đã bị phá hủy hoàn toàn! Hãy bấm nút Sửa chữa (Repair) để"
          " hồi phục.",
          ephemeral=True,
      )

    await interaction.response.defer()

    wt_event = random.choice([
        (
            "🛡️ **NON-PEN!** (Không xuyên giáp)",
            "Đạn bật ra khỏi lớp giáp góc nghiêng của địch mà không gây"
            " tổn hại!",
            0,
        ),
        (
            "🎯 **HIT!**",
            "Đạn xuyên thủng lớp giáp mỏng, gây tổn thất khoang chiến đấu!",
            25,
        ),
        (
            "💥 **CRITICAL HIT!**",
            "Phá hủy bộ phận quan trọng và làm bị thương kíp lái đối phương!",
            50,
        ),
        (
            "🔥 **TARGET DESTROYED!**",
            "Đạn trúng kho đạn, xe địch phát nổ tung thành mảnh vụn!",
            100,
        ),
    ])

    enemy_dmg = 0
    enemy_reaction = ""

    if wt_event[0] != "🔥 **TARGET DESTROYED!**":
      enemy_action = random.choice([
          (
              "Địch bắn trượt!",
              "Kẻ địch khai hỏa vội vã nhưng đạn bay sạt qua tháp pháo của chúng"
              " ta.",
              0,
          ),
          (
              "Địch bắn trúng gây sát thương!",
              "Kẻ địch phản công chính xác, đạn pháo xuyên qua giáp sườn!",
              30,
          ),
          (
              "Địch bắn hỏng xích!",
              "Phát bắn của địch cắt đứt xích xe, làm giảm khả năng cơ động!",
              15,
          ),
      ])
      enemy_dmg = enemy_action[2]
      self.hp = max(0, self.hp - enemy_dmg)
      enemy_reaction = f"\n\n⚠️ **KẺ ĐỊCH PHẢN CÔNG:** {enemy_action[0]} *{enemy_action[1]}* (Nhận -{enemy_dmg}% HP)"
    else:
      enemy_reaction = "\n\n✨ **Mục tiêu đã bị tiêu diệt hoàn toàn, không thể phản công!**"

    if self.hp <= 0:
      self.status = "Bị phá hủy (Wrecked)"
    elif enemy_dmg > 0:
      self.status = "Bị hư hại"
    else:
      self.status = "Ổn định"

    prompt = (
        f"Sĩ quan {interaction.user.name} dùng xe tăng {self.tank_name} thực"
        f" hiện: '{action_desc}'. Kết quả: {wt_event[0]}. Phản công từ địch:"
        f" {enemy_reaction}. Hãy mô tả diễn biến trận đấu qua kính ngắm FCS với"
        " văn phong sắc sảo, có chút lo lắng hoặc hồi hộp đặc trưng của Yuri."
    )

    try:
      response = ai_client.models.generate_content(
          model="gemini-3.6-flash",
          contents=prompt,
          config=types.GenerateContentConfig(
              system_instruction=YURI_MILITARY_SYSTEM_PROMPT
          ),
      )
      report = (
          response.text
          if response and response.text
          else "Đường đạn giao tranh ác liệt trên chiến tuyến."
      )
    except Exception as e:
      report = f"Lỗi tính toán chiến thuật: {e}"

    screen_art = generate_fcs_view(
        self.tank_name,
        self.turret_dir,
        self.speed,
        self.ammo,
        self.hp,
        self.status,
    )

    embed = discord.Embed(
        title=f"🔭 KÍNH NGẮM FCS — Lượt đánh: {action_desc}",
        description=(
            f"**Kết quả bắn:** {wt_event[0]} - *{wt_event[1]}*"
            f"{enemy_reaction}\n\n*{report}*\n```text\n{screen_art}\n```"
        ),
        color=discord.Color.dark_red(),
    )
    embed.add_field(name="🛡️ Khí tài", value=self.tank_name, inline=True)
    embed.add_field(name="❤️ Độ bền", value=f"{self.hp}%", inline=True)
    await interaction.message.edit(embed=embed, view=self)

  @discord.ui.button(
      label="🔄 Xoay tháp pháo 3 giờ", style=discord.ButtonStyle.secondary
  )
  async def btn_turret_3(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    self.turret_dir = "3 giờ (Sườn phải)"
    await self.process_fcs_action(interaction, "Quay tháp pháo hướng 3 giờ")

  @discord.ui.button(
      label="🔄 Xoay tháp pháo 9 giờ", style=discord.ButtonStyle.secondary
  )
  async def btn_turret_9(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    self.turret_dir = "9 giờ (Sườn trái)"
    await self.process_fcs_action(interaction, "Quay tháp pháo hướng 9 giờ")

  @discord.ui.button(
      label="🚀 Nạp đạn APFSDS", style=discord.ButtonStyle.danger
  )
  async def btn_apfsds(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    self.ammo = "APFSDS"
    await self.process_fcs_action(interaction, "Khai hỏa đạn APFSDS")

  @discord.ui.button(label="💥 Nạp đạn HE", style=discord.ButtonStyle.primary)
  async def btn_he(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    self.ammo = "HE"
    await self.process_fcs_action(interaction, "Khai hỏa đạn phá mảnh HE")

  @discord.ui.button(
      label="🔧 Sửa chữa (Repair)", style=discord.ButtonStyle.success
  )
  async def btn_repair(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    if interaction.user != self.ctx.author:
      return await interaction.response.send_message(
          "⚠️ Không có quyền!", ephemeral=True
      )
    await interaction.response.defer()
    self.hp = min(100, self.hp + 50)
    self.status = "Đã khắc phục sự cố"
    screen_art = generate_fcs_view(
        self.tank_name,
        self.turret_dir,
        self.speed,
        self.ammo,
        self.hp,
        self.status,
    )
    embed = discord.Embed(
        title="🔧 KHOA HỤC KỸ THUẬT - SỬA CHỮA KHẨN CẤP",
        description=(
            "Đội ngũ kỹ thuật viên dã chiến đã khẩn trương hàn gắn vết thủng và"
            f" hồi phục hệ thống!\n```text\n{screen_art}\n```"
        ),
        color=discord.Color.green(),
    )
    await interaction.message.edit(embed=embed, view=self)


# ================= 4. CÁC LỆNH HƯỚNG DẪN =================
@bot.command(name="Yhelps")
async def y_helps(ctx):
  embed = discord.Embed(
      title="📜 SỔ TAY CHIẾN DỊCH NGA - UKRAINE",
      description="Hướng dẫn lệnh chọn phe và triển khai khí tài:",
      color=discord.Color.dark_red(),
  )
  embed.add_field(
      name="1. Khởi động chiến dịch",
      value="`!campaign` - Mở bản đồ chiến sự.",
      inline=False,
  )
  embed.add_field(
      name="2. Chọn phe",
      value="`!Yteam Nga` hoặc `!Yteam Uka` - Lựa chọn phe tham chiến.",
      inline=False,
  )
  embed.add_field(
      name="3. Xuất chiến",
      value="`!deploy [tên xe]` - Đưa xe tăng vào tuyến đầu.",
      inline=False,
  )
  await ctx.send(embed=embed)


@bot.command(name="Y2.5Dhelps")
async def y_25d_helps(ctx):
  embed = discord.Embed(
      title="🎯 HƯỚNG DẪN KÍNH NGẮM FCS & TURN-BASED",
      description="`!fcs` để mở kính ngắm pháo thủ và chiến đấu theo lượt.",
      color=discord.Color.purple(),
  )
  await ctx.send(embed=embed)


# ================= 5. CÁC LỆNH CHIẾN DỊCH VĨ MÔ =================
@bot.command(name="campaign")
async def campaign(ctx):
  guild_id = ctx.guild.id
  game_sessions[guild_id] = {"team": None, "tanks": []}

  embed = discord.Embed(
      title="🌐 THÔNG BÁO TỪ STAVKA: MẶT TRẬN NGA - UKRAINE",
      description=(
          "Yuri khẽ đẩy gọng kính, trải bản đồ chiến sự Đông Âu lên bàn:\n'*Đồng"
          " chí sĩ quan, chiến trường đã sẵn sàng! Vui lòng chọn phe tham chiến"
          " bằng lệnh **`!Yteam Nga`** hoặc **`!Yteam Uka`** nhé...*'"
      ),
      color=discord.Color.red(),
  )
  await ctx.send(embed=embed)


@bot.command(name="Yteam")
async def y_team(ctx, team_name: str):
  guild_id = ctx.guild.id
  team_name_lower = team_name.capitalize()

  if team_name_lower not in ["Nga", "Uka"]:
    return await ctx.send(
        "⚠️ Lựa chọn không hợp lệ! Vui lòng gõ chính xác: `!Yteam Nga` hoặc"
        " `!Yteam Uka`."
    )

  if guild_id not in game_sessions:
    game_sessions[guild_id] = {"tanks": []}

  game_sessions[guild_id]["team"] = team_name_lower
  tanks_in_kho = ", ".join([f"`{t}`" for t in TEAM_TANKS[team_name_lower]])

  embed = discord.Embed(
      title=f"🎖️ ĐÃ XÁC NHẬN GIA NHẬP PHE: {team_name_lower.upper()}",
      description=(
          f"Yuri mỉm cười gật đầu:\n'*Tuyệt vời! Đồng chí đã chọn phe"
          f" **{team_name_lower}**. Dưới đây là danh sách khí tài sẵn sàng trong"
          f" kho của chúng ta:\n{tanks_in_kho}\n\nHãy dùng lệnh **`!deploy [tên"
          " xe]`** để xuất chiến ngay lập tức nhé!*'"
      ),
      color=discord.Color.blue(),
  )
  await ctx.send(embed=embed)


@bot.command(name="deploy")
async def deploy(ctx, tank_model: str, sector: str = "Tuyến đầu"):
  guild_id = ctx.guild.id

  # Kiểm tra xem đã tạo chiến dịch và chọn phe chưa
  if guild_id not in game_sessions or not game_sessions[guild_id].get("team"):
    return await ctx.send(
        "⚠️ Đồng chí chưa chọn phe! Vui lòng gõ `!campaign` rồi dùng `!Yteam Nga`"
        " hoặc `!Yteam Uka` trước."
    )

  current_team = game_sessions[guild_id]["team"]
  allowed_tanks = TEAM_TANKS[current_team]

  # Kiểm tra xem xe tăng có nằm trong kho của phe đó không (so sánh chữ thường)
  if tank_model.lower() not in allowed_tanks:
    tanks_str = ", ".join([f"`{t}`" for t in allowed_tanks])
    return await ctx.send(
        f"❌ **Báo động từ Bộ tham mưu!** Khí tài `{tank_model}` **không có thực"
        f" hoặc không thuộc biên chế** của phe {current_team} trong chiến dịch"
        f" này!\n\n📦 **Danh sách xe tăng hợp lệ của phe {current_team}:**"
        f" {tanks_str}"
    )

  # Nếu hợp lệ, tiến hành deploy
  game_sessions[guild_id]["tanks"].append(
      {"model": tank_model, "sector": sector}
  )
  await ctx.send(
      f"🛡️ **Biên chế thành công!** Khí tài **{tank_model}** đã tiến vào chốt"
      f" **{sector}**. Sẵn sàng kích hoạt lệnh `!fcs` để chiến đấu!"
  )


@bot.command(name="status")
async def status(ctx):
  guild_id = ctx.guild.id
  if guild_id not in game_sessions:
    return await ctx.send(
        "❌ Chưa có chiến dịch nào! Hãy gõ `!campaign` để bắt đầu."
    )

  session = game_sessions[guild_id]
  team_display = session.get("team", "Chưa chọn")
  tank_list = (
      ", ".join([f"{t['model']} ({t['sector']})" for t in session["tanks"]])
      if session["tanks"]
      else "Chưa triển khai xe nào"
  )

  embed = discord.Embed(
      title="📊 BÁO CÁO HẬU CẦN CHIẾN TRƯỜNG",
      color=discord.Color.gold(),
  )
  embed.add_field(name="🛡️ Phe tham chiến", value=team_display, inline=True)
  embed.add_field(name="🚀 Xe tăng trực chiến", value=tank_list, inline=False)
  await ctx.send(embed=embed)


# ================= 6. LỆNH KÍNH NGẮM FCS & TURN-BASED =================
@bot.command(name="fcs")
async def fcs(ctx):
  guild_id = ctx.guild.id
  tank_model = "T-90M"

  if guild_id in game_sessions and game_sessions[guild_id]["tanks"]:
    tank_model = game_sessions[guild_id]["tanks"][-1]["model"]

  initial_screen = generate_fcs_view(
      tank_model,
      turret_dir="12 giờ",
      speed="Đứng yên",
      ammo="APFSDS",
      hp=100,
      status="Sẵn sàng",
  )

  embed = discord.Embed(
      title="🔭 HỆ THỐNG KÍNH NGẮM FCS (TURN-BASED COMBAT)",
      description=(
          f"Yuri thì thầm:\n'*Đồng chí đang điều khiển chiếc **{tank_model}**"
          " đối đầu với kẻ địch. Mỗi lệnh bắn sẽ kích hoạt phản công theo"
          " lượt... Hãy cẩn thận nhé!*'\n```text\n{initial_screen}\n```"
      ),
      color=discord.Color.dark_purple(),
  )

  view = QuickChatFCSView(ctx, tank_model)
  await ctx.send(embed=embed, view=view)


# ================= 7. KHI BOT SẴN SÀNG =================
@bot.event
async def on_ready():
  print(
      f"✅ Nữ Sĩ quan Yuri (Verification Mode) đã trực chiến: {bot.user.name}"
  )


if __name__ == "__main__":
  keep_alive()
  bot.run(DISCORD_TOKEN)
