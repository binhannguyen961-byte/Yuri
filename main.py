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
  return "Yuri's Command Center is operational..."


def run_flask():
  port = int(os.environ.get("PORT", 8080))
  app.run(host="0.0.0.0", port=port)


def keep_alive():
  server_thread = threading.Thread(target=run_flask)
  server_thread.daemon = True
  server_thread.start()


# ================= 2. CẤU HÌNH BOT & GEMINI =================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "YOUR_DISCORD_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY")

ai_client = genai.Client(api_key=GEMINI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# Lưu trữ trạng thái game chiến dịch vĩ mô của từng server/người chơi
game_sessions = {}


# ================= 3. GIAO DIỆN NÚT BẤM 2.5D (TACTICAL VIEWER) =================
class TacticalControlView(discord.ui.View):

  def __init__(self, ctx, unit_name, sector):
    super().__init__(timeout=180)
    self.ctx = ctx
    self.unit_name = unit_name
    self.sector = sector

  async def process_action(self, interaction: discord.Interaction, action: str):
    if interaction.user != self.ctx.author:
      return await interaction.response.send_message(
          "⚠️ Đây không phải quyền ra lệnh của bạn!", ephemeral=True
      )

    await interaction.response.defer()

    # Dùng Gemini AI để mô phỏng diễn biến trận chiến 2.5D dựa trên lệnh của sĩ quan
    prompt = (
        f"Sĩ quan {interaction.user.name} đang chỉ huy đơn vị {self.unit_name}"
        f" tại khu vực {self.sector} với chiến lệnh: '{action}'. "
        "Hãy đóng vai trò là hệ thống mô phỏng chiến trường 2.5D kiểu quân sự,"
        " viết một bản báo cáo ngắn gọn (khoảng 3-4 câu) mô tả diễn biến chiến"
        " đấu, hiệu quả hỏa lực, thiệt hại của địch và tình trạng hiện tại của"
        " đơn vị theo phong cách nghiêm túc, kịch tính."
    )

    try:
      response = ai_client.models.generate_content(
          model="gemini-3.6-flash",
          contents=prompt,
          config=types.GenerateContentConfig(
              system_instruction=(
                  "Bạn là hệ thống máy tính chiến thuật quân sự tối tân."
              )
          ),
      )
      report = (
          response.text
          if response and response.text
          else "Cuộc giao tranh diễn ra ác liệt nhưng chưa có kết quả rõ ràng."
      )
    except Exception as e:
      report = f"Lỗi hệ thống chiến thuật: {e}"

    embed = discord.Embed(
        title=f"📊 BÁO CÁO CHIẾN TRƯỜNG 2.5D - Lệnh: {action}",
        description=report,
        color=discord.Color.dark_red(),
    )
    embed.add_field(name="Đơn vị chủ lực", value=self.unit_name, inline=True)
    embed.add_field(name="Khu vực tác chiến", value=self.sector, inline=True)

    for child in self.children:
      child.disabled = True

    await interaction.message.edit(embed=embed, view=self)

  @discord.ui.button(
      label="🔥 Pháo kích tổng lực", style=discord.ButtonStyle.danger
  )
  bt_fire(self, interaction, button):
    await self.process_action(interaction, "Pháo kích tổng lực")

  @discord.ui.button(
      label="🛡️ Phòng thủ bọc thép", style=discord.ButtonStyle.primary
  )
  bt_defend(self, interaction, button):
    await self.process_action(interaction, "Phòng thủ bọc thép kiên cố")

  @discord.ui.button(
      label="⚡ Đột phá bọc sườn", style=discord.ButtonStyle.success
  )
  bt_flank(self, interaction, button):
    await self.process_action(interaction, "Đột phá bọc sườn chớp nhoáng")


# ================= 4. LỆNH HƯỚNG DẪN (!Yhelps & !Y2.5Dhelps) =================
@bot.command(name="Yhelps")
async def y_helps(ctx):
  embed = discord.Embed(
      title="🗺️ SỔ TAY CHIẾN DỊCH VĨ MÔ (World Conqueror Style)",
      description=(
          "Hướng dẫn điều phối lực lượng và quản lý chiến dịch quân sự toàn"
          " cầu:"
      ),
      color=discord.Color.blue(),
  )
  embed.add_field(
      name="1. Khởi động chiến dịch",
      value=(
          "`!campaign [tên chiến dịch]` - Mở bản đồ chiến sự mới.\nVí dụ:"
          " `!campaign Đông Âu 2026`"
      ),
      inline=False,
  )
  embed.add_field(
      name="2. Triển khai khí tài",
      value=(
          "`!deploy [Tên khí tài] [Khu vực]` - Đưa xe tăng, pháo binh ra mặt"
          " trận.\nVí dụ: `!deploy T-90M SectorA`"
      ),
      inline=False,
  )
  embed.add_field(
      name="3. Kiểm tra hậu cần",
      value=(
          "`!status` - Kiểm tra thông số tài nguyên, đạn dược và trạng thái"
          " quân đội."
      ),
      inline=False,
  )
  await ctx.send(embed=embed)


@bot.command(name="Y2.5Dhelps")
async def y_25d_helps(ctx):
  embed = discord.Embed(
      title="🎯 HƯỚNG DẪN MINI-GAME TÁC CHIẾN 2.5D (Góc nhìn Sĩ quan)",
      description="Hướng dẫn trực tiếp điều khiển chiến trường thời gian thực:",
      color=discord.Color.orange(),
  )
  embed.add_field(
      name="1. Mở phòng tác chiến 2.5D",
      value=(
          "`!tactical [Tên đơn vị] [Khu vực]`\nVí dụ: `!tactical 2S7-Pion"
          " Tiền_Tuyến_Bắc`"
      ),
      inline=False,
  )
  embed.add_field(
      name="2. Hệ thống ra lệnh trực quan",
      value=(
          "Khi lệnh được bật, một bảng thông tin 2.5D xuất hiện kèm các nút"
          " bấm tương tác:\n- **Pháo kích tổng lực:** Tiêu diệt diện rộng nhưng"
          " tốn đạn.\n- **Phòng thủ bọc thép:** Giảm thiểu thiệt hại trước hỏa"
          " lực địch.\n- **Đột phá bọc sườn:** Tấn công bất ngờ gây hỗn loạn hàng"
          " ngũ đối phương."
      ),
      inline=False,
  )
  await ctx.send(embed=embed)


# ================= 5. CÁC LỆNH CHIẾN DỊCH VĨ MÔ =================
@bot.command(name="campaign")
async def campaign(ctx, *, name: str = "Mặt trận chung"):
  guild_id = ctx.guild.id
  game_sessions[guild_id] = {
      "name": name,
      "fuel": 1000,
      "ammo": 500,
      "units": [],
  }
  embed = discord.Embed(
      title=f"🌐 CHIẾN DỊCH KHỞI ĐỘNG: {name}",
      description=(
          "Bộ Tổng tham mưu đã thiết lập bản đồ chiến sự thành công!\nTrạng"
          " thái tài nguyên ban đầu:\n⛽ **Nhiên liệu:** 1000 | 📦 **Đạn dược:**"
          " 500"
      ),
      color=discord.Color.green(),
  )
  await ctx.send(embed=embed)


@bot.command(name="deploy")
async def deploy(ctx, unit: str, sector: str):
  guild_id = ctx.guild.id
  if guild_id not in game_sessions:
    game_sessions[guild_id] = {
        "name": "Mặt trận mặc định",
        "fuel": 1000,
        "ammo": 500,
        "units": [],
    }

  game_sessions[guild_id]["units"].append({"unit": unit, "sector": sector})
  await ctx.send(
      f"🚀 **Điều phối thành công!** Đơn vị **{unit}** đã tiến vào giữ chốt"
      f" tại khu vực **{sector}**."
  )


@bot.command(name="status")
async def status(ctx):
  guild_id = ctx.guild.id
  if guild_id not in game_sessions:
    return await ctx.send(
        "❌ Chưa có chiến dịch nào được khởi động. Hãy dùng `!campaign` trước"
        " nhé!"
    )

  session = game_sessions[guild_id]
  unit_list = (
      ", ".join([f"{u['unit']} ({u['sector']})" for u in session["units"]])
      if session["units"]
      else "Chưa có đơn vị triển khai"
  )

  embed = discord.Embed(
      title=f"📊 TRẠNG THÁI CHIẾN DỊCH: {session['name']}",
      color=discord.Color.gold(),
  )
  embed.add_field(name="⛽ Nhiên liệu", value=session["fuel"], inline=True)
  embed.add_field(name="📦 Đạn dược", value=session["ammo"], inline=True)
  embed.add_field(name="🛡️ Đội hình hiện tại", value=unit_list, inline=False)
  await ctx.send(embed=embed)


# ================= 6. LỆNH MỞ PHÒNG TÁC CHIẾN 2.5D =================
@bot.command(name="tactical")
async def tactical(ctx, unit_name: str, sector: str):
  embed = discord.Embed(
      title="📡 PHÒNG TÁC CHIẾN 2.5D - TRUNG TÂM CHỈ HUY",
      description=(
          f"Đơn vị chủ lực **{unit_name}** đang tiếp cận khu vực **{sector}**."
          " Trinh sát phát hiện mục tiêu địch trong tầm ngắm. Sĩ quan"
          f" **{ctx.author.name}** hãy đưa ra chiến lệnh tác chiến ngay lập"
          " tức!"
      ),
      color=discord.Color.purple(),
  )
  view = TacticalControlView(ctx, unit_name, sector)
  await ctx.send(embed=embed, view=view)


# ================= 7. KHI BOT SẴN SÀNG =================
@bot.event
async def on_ready():
  print(f"✅ Bot Yuri Chiến Thuật đã hoạt động: {bot.user.name}")


if __name__ == "__main__":
  keep_alive()
  bot.run(DISCORD_TOKEN)
