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
  return "Soviet Red Army Command Center is operational..."


def run_flask():
  port = int(os.environ.get("PORT", 8080))
  app.run(host="0.0.0.0", port=port)


def keep_alive():
  server_thread = threading.Thread(target=run_flask)
  server_thread.daemon = True
  server_thread.start()


# ================= 2. CẤU HÌNH BOT & GEMINI (HỒNG QUÂN SOVIET) =================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "YOUR_DISCORD_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY")

ai_client = genai.Client(api_key=GEMINI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# Lưu trữ trạng thái chiến dịch vĩ mô và bàn đồ 2.5D của các server
game_sessions = {}

SOVIET_OFFICER_SYSTEM_PROMPT = (
    "Bạn là Yuri - Nữ Sĩ quan Tham mưu cấp cao của Hồng Quân Liên Xô trong thời kỳ"
    " Chiến tranh Lạnh. Tính cách của bạn: Kỷ luật thép, nghiêm túc, sắc sảo,"
    " trung thành tuyệt đối với lý tưởng, nói năng dứt khoát mang đậm chất quân"
    " sự Liên Xô. Khi người dùng ra lệnh chiến đấu trên bản đồ 2.5D, hãy đưa ra"
    " báo cáo chiến trường kịch tính, đánh giá hiệu quả hỏa lực tiêu diệt kẻ địch"
    " tư bản."
)


# ================= 3. GIAO DIỆN BẢN ĐỒ 2.5D RETRO (DOOM/TACTICAL STYLE) =================
def generate_ascii_map(unit_name, sector, enemy_status="Đang tiến công"):
  # Bản đồ chiến trường 2.5D mô phỏng góc nhìn sĩ quan (Retro ASCII Grid)
  map_art = f"""
╔════════════════════════════════════════════╗
║ [RADAR STAVKA] KHU VỰC: {sector.upper()}          ║
╠════════════════════════════════════════════╣
║  [Địch: Tư Bản]                           ║
║       v      v      v                      ║
║     [ T-72 ] [ BMP ] [ VÒNG PHÒNG THỦ ]    ║
║  ----------------------------------------  ║
║     [ {unit_name[:8]} ] <--- VỊ TRÍ TA     ║
║       ^      ^      ^                      ║
║  [HẬU CƯƠNG & TIẾP TẾ - TRẠM CHỈ HUY]      ║
╚════════════════════════════════════════════╝
Trạng thái địch: {enemy_status}
"""
  return map_art


class TacticalControlView(discord.ui.View):

  def __init__(self, ctx, unit_name, sector):
    super().__init__(timeout=180)
    self.ctx = ctx
    self.unit_name = unit_name
    self.sector = sector

  async def process_action(self, interaction: discord.Interaction, action: str):
    if interaction.user != self.ctx.author:
      return await interaction.response.send_message(
          "⚠️ Cảnh cáo! Đồng chí không có quyền can thiệp vào quyền chỉ huy này!",
          ephemeral=True,
      )

    await interaction.response.defer()

    prompt = (
        f"Đồng chí sĩ quan {interaction.user.name} vừa ra lệnh cho đơn vị"
        f" {self.unit_name} tại khu vực {self.sector}: '{action}'. "
        "Hãy viết một bản báo cáo chiến trường ngắn gọn (khoảng 3 câu) với tư"
        " cách là Sĩ quan tham mưu Liên Xô, mô tả hỏa lực hủy diệt kẻ địch và"
        " cập nhật tình hình chiến tuyến."
    )

    try:
      response = ai_client.models.generate_content(
          model="gemini-3.6-flash",
          contents=prompt,
          config=types.GenerateContentConfig(
              system_instruction=SOVIET_OFFICER_SYSTEM_PROMPT
          ),
      )
      report = (
          response.text
          if response and response.text
          else "Hỏa lực đã trúng đích, kẻ địch rút lui hỗn loạn!"
      )
    except Exception as e:
      report = f"Lỗi đường truyền Stavka: {e}"

    updated_map = generate_ascii_map(
        self.unit_name, self.sector, enemy_status="Đã bị tiêu diệt / Rút lui"
    )

    embed = discord.Embed(
        title=f"⭐ BÁO CÁO TÁC CHIẾN 2.5D — Lệnh: {action}",
        description=f"*{report}*\n```text\n{updated_map}\n```",
        color=discord.Color.red(),
    )
    embed.add_field(name="🏛️ Đơn vị chủ lực", value=self.unit_name, inline=True)
    embed.add_field(name="📍 Khu vực", value=self.sector, inline=True)
    embed.set_footer(text="Vì Tổ quốc xã hội chủ nghĩa! Chiến thắng!")

    for child in self.children:
      child.disabled = True

    await interaction.message.edit(embed=embed, view=self)

  @discord.ui.button(
      label="🔥 Pháo kích Katyusha / 2S7", style=discord.ButtonStyle.danger
  )
  async def bt_fire(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await self.process_action(
        interaction, "Khai hỏa pháo binh tổng lực (Katyusha/2S7 Pion)"
    )

  @discord.ui.button(
      label="🛡️ Thiết lập tường thép", style=discord.ButtonStyle.primary
  )
  async def bt_defend(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await self.process_action(interaction, "Thiết lập tuyến phòng thủ bọc thép")

  @discord.ui.button(
      label="⚡ Đột phá bọc sườn", style=discord.ButtonStyle.success
  )
  async def bt_flank(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await self.process_action(
        interaction, "Tấn công bọc sườn bão táp bằng cơ giới hóa"
    )


# ================= 4. LỆNH HƯỚNG DẪN (!Yhelps & !Y2.5Dhelps) =================
@bot.command(name="Yhelps")
async def y_helps(ctx):
  embed = discord.Embed(
      title="📜 SỔ TAY HỌC THUYẾT QUÂN SỰ LIÊN XÔ (World Conqueror Style)",
      description=(
          "Chào mừng đồng chí đến với Bộ Tổng tham mưu Hồng Quân. Dưới đây là"
          " các chỉ thị chiến dịch vĩ mô:"
      ),
      color=discord.Color.dark_red(),
  )
  embed.add_field(
      name="1. Khởi động chiến dịch toàn cầu",
      value=(
          "`!campaign [Tên mặt trận]` - Thiết lập bản đồ tác chiến mới.\nVí"
          " dụ: `!campaign Mặt_Trận_Đông_Âu`"
      ),
      inline=False,
  )
  embed.add_field(
      name="2. Triển khai khí tài chiến lược",
      value=(
          "`!deploy [Tên đơn vị] [Khu vực]` - Điều động xe tăng, pháo tự hành"
          " ra tiền tuyến.\nVí dụ: `!deploy T-90M Sector-Alpha`"
      ),
      inline=False,
  )
  embed.add_field(
      name="3. Kiểm tra tình trạng hậu cần",
      value=(
          "`!status` - Kiểm kho dự trữ nhiên liệu, đạn dược và đội hình chiến"
          " đấu."
      ),
      inline=False,
  )
  embed.set_footer(text="Nghiêm chỉnh chấp hành điều lệnh quân đội!")
  await ctx.send(embed=embed)


@bot.command(name="Y2.5Dhelps")
async def y_25d_helps(ctx):
  embed = discord.Embed(
      title="🎯 CHỈ THỊ PHÒNG TÁC CHIẾN 2.5D (Góc nhìn Sĩ quan Hồng Quân)",
      description=(
          "Hướng dẫn trực tiếp điều phối hỏa lực qua bản đồ mô phỏng kiểu"
          " Retro:"
      ),
      color=discord.Color.orange(),
  )
  embed.add_field(
      name="1. Mở trung tâm tác chiến 2.5D",
      value=(
          "`!tactical [Tên đơn vị] [Khu vực]`\nVí dụ: `!tactical 2S7-Pion"
          " Tiền_Tuyến_Bắc`"
      ),
      inline=False,
  )
  embed.add_field(
      name="2. Giao diện bản đồ trực quan",
      value=(
          "Hệ thống sẽ render một màn hình radar chiến trường dạng ASCII kèm"
          " các nút điều khiển chiến thuật thời gian thực để đồng chí tiêu diệt"
          " mục tiêu."
      ),
      inline=False,
  )
  embed.set_footer(text="Vinh quang thuộc về Hồng Quân Liên Xô!")
  await ctx.send(embed=embed)


# ================= 5. CÁC LỆNH CHIẾN DỊCH VĨ MÔ =================
@bot.command(name="campaign")
async def campaign(ctx, *, name: str = "Mặt trận Chiến tranh Lạnh"):
  guild_id = ctx.guild.id
  game_sessions[guild_id] = {
      "name": name,
      "fuel": 2000,
      "ammo": 1500,
      "units": [],
  }
  embed = discord.Embed(
      title=f"🔴 THÔNG CÁO TỪ STAVKA: KHỞI ĐỘNG CHIẾN DỊCH [{name}]",
      description=(
          "Bộ Tổng tham mưu đã phê duyệt kế hoạch tác chiến chiến lược!\nKho"
          " dự trữ hậu cần tiếp viện:\n⛽ **Nhiên liệu cơ giới:** 2000 tấn | 📦"
          " **Đạn dược pháo binh:** 1500 hòm"
      ),
      color=discord.Color.red(),
  )
  await ctx.send(embed=embed)


@bot.command(name="deploy")
async def deploy(ctx, unit: str, sector: str):
  guild_id = ctx.guild.id
  if guild_id not in game_sessions:
    game_sessions[guild_id] = {
        "name": "Mặt trận mặc định",
        "fuel": 2000,
        "ammo": 1500,
        "units": [],
    }

  game_sessions[guild_id]["units"].append({"unit": unit, "sector": sector})
  await ctx.send(
      f"🎖️ **Mệnh lệnh đã thực thi!** Sư đoàn/Khí tài **{unit}** đã tiếp quản"
      " hoàn toàn khu vực **{sector}**. Sẵn sàng nhận chiến dịch."
  )


@bot.command(name="status")
async def status(ctx):
  guild_id = ctx.guild.id
  if guild_id not in game_sessions:
    return await ctx.send(
        "❌ Cảnh cáo đồng chí! Chưa có chiến dịch nào được khởi động. Hãy dùng"
        " lệnh `!campaign` trước!"
    )

  session = game_sessions[guild_id]
  unit_list = (
      ", ".join([f"{u['unit']} ({u['sector']})" for u in session["units"]])
      if session["units"]
      else "Chưa có đơn vị triển khai"
  )

  embed = discord.Embed(
      title=f"📊 BÁO CÁO HẬU CẦN MẶT TRẬN: {session['name']}",
      color=discord.Color.gold(),
  )
  embed.add_field(name="⛽ Nhiên liệu chiến lược", value=session["fuel"], inline=True)
  embed.add_field(name="📦 Hòm đạn pháo", value=session["ammo"], inline=True)
  embed.add_field(name="🛡️ Đội hình sư đoàn trực chiến", value=unit_list, inline=False)
  await ctx.send(embed=embed)


# ================= 6. LỆNH MỞ PHÒNG TÁC CHIẾN 2.5D (RETRO MAP) =================
@bot.command(name="tactical")
async def tactical(ctx, unit_name: str, sector: str):
  ascii_art = generate_ascii_map(unit_name, sector, enemy_status="Đang áp sát")

  embed = discord.Embed(
      title="⭐ TRUNG TÂM CHỈ HUY TÁC CHIẾN 2.5D",
      description=(
          f"Báo cáo đồng chí **{ctx.author.name}**! Đơn vị **{unit_name}** đã"
          f" vào vị trí. Màn hình radar quét được:\n```text\n{ascii_art}\n```"
          " Mời đồng chí hạ quyết tâm chiến thuật bằng các nút bên dưới!"
      ),
      color=discord.Color.dark_red(),
  )
  view = TacticalControlView(ctx, unit_name, sector)
  await ctx.send(embed=embed, view=view)


# ================= 7. KHI BOT SẴN SÀNG =================
@bot.event
async def on_ready():
  print(
      f"✅ Nữ Sĩ quan Yuri Liên Xô đã vào vị trí trực chiến: {bot.user.name}"
  )


if __name__ == "__main__":
  keep_alive()
  bot.run(DISCORD_TOKEN)
