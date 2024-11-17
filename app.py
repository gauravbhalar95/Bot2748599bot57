import os
import logging
import threading
import discord
from discord.ext import commands
from flask import Flask, request
import telebot
import yt_dlp
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
import asyncio

# Load API tokens and channel IDs from environment variables
API_TOKEN_2 = os.getenv('API_TOKEN_2')
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')  # Your Telegram Channel ID with @ like '@YourChannel'

# Initialize the Telegram bot with debug mode enabled
bot2 = telebot.TeleBot(API_TOKEN_2, parse_mode='HTML')
telebot.logger.setLevel(logging.DEBUG)

# Initialize the Discord bot
intents = discord.Intents.default()
intents.messages = True
discord_bot = commands.Bot(command_prefix="!", intents=intents)

# Directory to save downloaded files
output_dir = 'downloads/'
cookies_file = 'cookies.txt'  # YouTube cookies file

# Ensure the downloads directory exists
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

# Ensure yt-dlp is updated
os.system('yt-dlp -U')

def sanitize_filename(filename, max_length=250):  # Reduce max_length if needed
    import re
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)  # Remove invalid characters
    return filename.strip()[:max_length]

# Function to validate URLs
def is_valid_url(url):
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

# Function to download media
def download_media(url, username=None, password=None):
    logging.debug(f"Attempting to download media from URL: {url}")

    # Set up options for yt-dlp with filename sanitization
    ydl_opts = {
        'format': 'best[ext=mp4]/best',  # Try mp4 format first
        'outtmpl': f'{output_dir}{sanitize_filename("%(title)s")}.%(ext)s',  # Use sanitized title
        'cookiefile': cookies_file,  # Use cookie file if required for authentication
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }],
        'socket_timeout': 10,
        'retries': 5,  # Retry on download errors
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.85 Safari/537.36'
    }

    if username and password:
        ydl_opts['username'] = username
        ydl_opts['password'] = password

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info_dict)

        if not os.path.exists(file_path):
            part_file_path = f"{file_path}.part"
            if os.path.exists(part_file_path):
                os.rename(part_file_path, file_path)
                logging.debug(f"Renamed partial file: {part_file_path} to {file_path}")
            else:
                logging.error(f"Downloaded file not found at path: {file_path}")
                raise Exception("Download failed: File not found after download.")

        return file_path

    except Exception as e:
        logging.error(f"yt-dlp download error: {str(e)}")
        raise

# Function to download media and send it asynchronously to Telegram
def download_and_send_telegram(message, url, username=None, password=None):
    if not is_valid_url(url):
        bot2.reply_to(message, "The provided URL is not valid. Please enter a valid URL.")
        return

    try:
        bot2.reply_to(message, "Downloading media, this may take some time...")
        logging.debug("Initiating media download")

        with ThreadPoolExecutor(max_workers=3) as executor:
            future = executor.submit(download_media, url, username, password)
            file_path = future.result()

            logging.debug(f"Download completed, file path: {file_path}")

            if file_path.lower().endswith('.mp4'):
                with open(file_path, 'rb') as media:
                    bot2.send_video(message.chat.id, media)
            else:
                with open(file_path, 'rb') as media:
                    if file_path.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                        bot2.send_photo(message.chat.id, media)
                    else:
                        bot2.send_document(message.chat.id, media)

            os.remove(file_path)
            bot2.reply_to(message, "Download and sending completed successfully.")

    except Exception as e:
        bot2.reply_to(message, f"Failed to download. Error: {str(e)}")
        logging.error(f"Download failed: {e}")

# Function to download media and send it asynchronously to Discord
async def download_and_send_discord(ctx, url, username=None, password=None):
    if not is_valid_url(url):
        await ctx.send("The provided URL is not valid. Please enter a valid URL.")
        return

    try:
        await ctx.send("Downloading media, this may take some time...")
        logging.debug("Initiating media download")

        file_path = download_media(url, username, password)

        logging.debug(f"Download completed, file path: {file_path}")

        if file_path.lower().endswith('.mp4'):
            with open(file_path, 'rb') as media:
                await ctx.send(file=discord.File(media))
        else:
            with open(file_path, 'rb') as media:
                if file_path.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                    await ctx.send(file=discord.File(media))
                else:
                    await ctx.send(file=discord.File(media))

        os.remove(file_path)
        await ctx.send("Download and sending completed successfully.")

    except Exception as e:
        await ctx.send(f"Failed to download. Error: {str(e)}")
        logging.error(f"Download failed: {e}")

# Function to handle messages from Telegram
@bot2.message_handler(func=lambda message: True)
def handle_telegram_links(message):
    url = message.text

    username = None
    password = None
    if "@" in url:
        username, password = url.split('@', 1)
        url = password

    threading.Thread(target=download_and_send_telegram, args=(message, url, username, password)).start()

# Discord bot command to download media
@discord_bot.command()
async def download(ctx, url: str):
    username = password = None
    if "@" in url:
        username, password = url.split('@', 1)
        url = password
    await download_and_send_discord(ctx, url, username, password)

# Flask app setup
app = Flask(__name__)

# Flask routes for webhook handling
@app.route('/' + API_TOKEN_2, methods=['POST'])
def getMessage_bot2():
    bot2.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "!", 200

@app.route('/')
def webhook():
    bot2.remove_webhook()
    bot2.set_webhook(url=os.getenv('KOYEB_URL') + '/' + API_TOKEN_2, timeout=60)
    return "Webhook set", 200

# Run both bots concurrently
async def run_bots():
    loop = asyncio.get_event_loop()
    loop.create_task(discord_bot.start(DISCORD_TOKEN))
    app.run(host='0.0.0.0', port=8080, debug=True)

if __name__ == "__main__":
    asyncio.run(run_bots())