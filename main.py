import discord
from discord import app_commands
import yt_dlp
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.voice_states = True

bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

# Cấu hình yt-dlp
ydl_opts = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'cookiefile': 'cookies.txt',
    'extractaudio': True,
    'audioquality': 1,
}

queues = {}
players = {}

class MusicPlayer:
    def __init__(self, voice_client):
        self.voice_client = voice_client
        self.queue = []
        self.current = None

    async def play_next(self):
        if not self.queue:
            self.current = None
            return

        url = self.queue.pop(0)
        self.current = url

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if 'entries' in info:
                    info = info['entries'][0]
                audio_url = info['url']
                title = info.get('title', 'Không rõ')

            source = discord.FFmpegPCMAudio(
                audio_url,
                executable="ffmpeg",
                before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                options="-vn"
            )
        except Exception as e:
            if "Sign in to confirm you're not a bot" in str(e):
                print("Lỗi cookies YouTube!")
                try:
                    await self.voice_client.channel.send("❌ Cookies YouTube hết hạn hoặc không hợp lệ. Vui lòng cập nhật lại file cookies.txt!")
                except:
                    pass
            raise e

            def after_playing(error):
                if error:
                    print(f"Lỗi: {error}")
                asyncio.run_coroutine_threadsafe(self.play_next(), bot.loop)

            self.voice_client.play(source, after=after_playing)
            print(f"Đang phát: {title}")
            try:
                channel = self.voice_client.channel
                if channel:
                    await channel.send(f"🎵 Đang phát: **{title}**")
            except:
                pass

        except Exception as e:
            print(f"Lỗi phát: {e}")
            await self.play_next()

@bot.event
async def on_ready():
    print(f"✅ Music Bot (Slash) đã online: {bot.user}")
    try:
        synced = await tree.sync()
        print(f"✅ Đã sync {len(synced)} slash commands!")
    except Exception as e:
        print(f"❌ Lỗi sync slash commands: {e}")

# ==================== SLASH COMMANDS ====================

@tree.command(name="join", description="Bot vào voice channel")
async def join(interaction: discord.Interaction):
    if interaction.user.voice:
        channel = interaction.user.voice.channel
        await channel.connect()
        await interaction.response.send_message(f"✅ Đã vào **{channel.name}**")
    else:
        await interaction.response.send_message("❌ Bạn phải vào voice channel trước!", ephemeral=True)

@tree.command(name="leave", description="Rời voice channel")
async def leave(interaction: discord.Interaction):
    if interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("👋 Đã rời voice channel")
    else:
        await interaction.response.send_message("❌ Bot không ở trong voice nào!", ephemeral=True)

async def play_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    if len(current) < 2:
        return []
    try:
        search_opts = {
            'quiet': True,
            'no_warnings': True,
            'default_search': 'ytsearch5',
            'cookiefile': 'cookies.txt',
        }
        with yt_dlp.YoutubeDL(search_opts) as ydl:
            info = ydl.extract_info(f"ytsearch5:{current}", download=False)
            results = []
            for entry in info.get('entries', [])[:5]:
                title = entry.get('title', 'Không rõ')[:100]
                results.append(app_commands.Choice(name=title, value=title))
            return results
    except:
        return []

@tree.command(name="play", description="Phát nhạc (YouTube)")
@app_commands.describe(query="Tên bài hát hoặc link YouTube")
@app_commands.autocomplete(query=play_autocomplete)
async def play(interaction: discord.Interaction, query: str):
    await interaction.response.defer()

    try:
        if not interaction.guild.voice_client:
            if interaction.user.voice:
                for attempt in range(3):
                    try:
                        await interaction.user.voice.channel.connect()
                        break
                    except Exception as e:
                        if attempt == 2:
                            raise e
                        await asyncio.sleep(2)
            else:
                await interaction.followup.send("❌ Bạn phải vào voice channel trước!")
                return

        guild_id = interaction.guild.id
        if guild_id not in queues:
            queues[guild_id] = []

        queues[guild_id].append(query)
        await interaction.followup.send(f"✅ Đã thêm vào hàng chờ: **{query}**")

        if not interaction.guild.voice_client.is_playing():
            player = MusicPlayer(interaction.guild.voice_client)
            players[guild_id] = player
            await player.play_next()

    except (discord.errors.ConnectionClosed, ConnectionRefusedError, OSError) as e:
        print(f"Lỗi voice connection: {e}")
        await interaction.followup.send("❌ Hosting đang gặp vấn đề kết nối voice. Thử lại sau 5-10 phút hoặc đổi hosting nhé!")
    except Exception as e:
        print(f"Lỗi play command: {e}")
        await interaction.followup.send("❌ Có lỗi xảy ra. Thử lại sau nhé!")

@tree.command(name="skip", description="Skip bài hiện tại")
async def skip(interaction: discord.Interaction):
    if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
        interaction.guild.voice_client.stop()
        await interaction.response.send_message("⏭️ Đã skip!")
    else:
        await interaction.response.send_message("❌ Không có bài nào đang phát!", ephemeral=True)

@tree.command(name="queue", description="Xem hàng chờ")
async def queue_cmd(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    if guild_id in queues and queues[guild_id]:
        q = "\n".join([f"{i+1}. {s}" for i, s in enumerate(queues[guild_id])])
        await interaction.response.send_message(f"📜 **Hàng chờ:**\n{q}")
    else:
        await interaction.response.send_message("📭 Hàng chờ trống!")

@tree.command(name="nowplaying", description="Bài đang phát")
async def nowplaying(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    if guild_id in players and players[guild_id].current:
        await interaction.response.send_message(f"🎵 Đang phát: **{players[guild_id].current}**")
    else:
        await interaction.response.send_message("❌ Không có bài nào đang phát!", ephemeral=True)

@tree.command(name="stop", description="Dừng nhạc + xóa hàng chờ")
async def stop(interaction: discord.Interaction):
    if interaction.guild.voice_client:
        interaction.guild.voice_client.stop()
        if interaction.guild.id in queues:
            queues[interaction.guild.id].clear()
        await interaction.response.send_message("⏹️ Đã dừng và xóa hàng chờ")
    else:
        await interaction.response.send_message("❌ Bot không đang phát nhạc!", ephemeral=True)

bot.run(os.getenv("TOKEN"))
