import os
import logging
from flask import Flask, request
import telebot
import yt_dlp
import re
from urllib.parse import urlparse
from mega import Mega
import time
import nest_asyncio

# Apply the patch for nested event loops
nest_asyncio.apply()

# Environment variables
API_TOKEN = os.getenv('BOT_TOKEN')  # Bot token
WEBHOOK_URL = os.getenv('WEBHOOK_URL')  # Webhook URL
CHANNEL_ID = os.getenv('CHANNEL_ID')
PORT = int(os.getenv('PORT', 8080))  # Default to 8080
COOKIES_FILE = 'cookies.txt'

# Initialize the bot
bot = telebot.TeleBot(API_TOKEN, parse_mode='HTML')

# Logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Directories
DOWNLOAD_DIR = 'downloads'
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Supported domains
SUPPORTED_DOMAINS = [
    'youtube.com', 'youtu.be', 'instagram.com', 'x.com',
    'facebook.com', 'xvideos.com', 'xnxx.com', 'xhamster.com'
]

# Mega client
mega_client = None

# Utility to sanitize filenames
def sanitize_filename(filename, max_length=250):
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)
    return filename.strip()[:max_length]

# Validate URLs
def is_valid_url(url):
    try:
        result = urlparse(url)
        return result.scheme in ['http', 'https'] and any(domain in result.netloc for domain in SUPPORTED_DOMAINS)
    except ValueError:
        return False

# Get streaming URL using yt-dlp
def get_streaming_url(url):
    ydl_opts = {
        'format': 'best',
        'noplaylist': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            return info_dict.get('url')
    except Exception as e:
        logger.error(f"Error fetching streaming URL: {e}")
        return None

# Download video using yt-dlp
def download_video(url, start_time=None, end_time=None):
    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'outtmpl': f'{DOWNLOAD_DIR}/{sanitize_filename("%(title)s")}.%(ext)s',
        'cookiefile': COOKIES_FILE if os.path.exists(COOKIES_FILE) else None,
        'postprocessors': [{'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'}],
        'socket_timeout': 10,
        'retries': 5,
    }
    if start_time and end_time:
        ydl_opts['postprocessor_args'] = ['-ss', start_time, '-to', end_time]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            return ydl.prepare_filename(info_dict)
    except Exception as e:
        logger.error(f"Error downloading video: {e}")
        return None

# Upload file to Mega.nz
def upload_to_mega(file_path):
    if not mega_client:
        raise Exception("Mega client is not logged in. Use /meganz <username> <password> to log in.")
    try:
        file = mega_client.upload(file_path)
        return mega_client.get_upload_link(file)
    except Exception as e:
        logger.error(f"Error uploading to Mega.nz: {e}")
        raise

# Command: /start
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "Welcome! Send me a video link to download or stream.")

# Command: /meganz
@bot.message_handler(commands=['meganz'])
def handle_mega_login(message):
    global mega_client
    args = message.text.split(maxsplit=2)
    try:
        if len(args) == 1:
            mega_client = Mega().login()  # Anonymous login
            bot.reply_to(message, "Logged in to Mega.nz anonymously!")
        elif len(args) == 3:
            email, password = args[1], args[2]
            mega_client = Mega().login(email, password)
            bot.reply_to(message, "Successfully logged in to Mega.nz!")
        else:
            bot.reply_to(message, "Usage: /meganz <username> <password> or /meganz for anonymous login")
    except Exception as e:
        bot.reply_to(message, f"Login failed: {str(e)}")

# Handle video download and streaming
@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_message(message):
    url = message.text.strip()
    if not is_valid_url(url):
        bot.reply_to(message, "Invalid or unsupported URL.")
        return

    bot.reply_to(message, "Processing your request, please wait...")

    # Get the streaming URL
    streaming_url = get_streaming_url(url)
    if not streaming_url:
        bot.reply_to(message, "Error: Unable to fetch a streaming URL.")
        return

    # Send streaming link
    try:
        bot.reply_to(message, f"Your video is ready for streaming:\n{streaming_url}")
    except Exception as e:
        logger.error(f"Error sending streaming URL: {e}")
        bot.reply_to(message, f"Error: {e}")

# Flask app for webhook
app = Flask(__name__)

@app.route('/' + API_TOKEN, methods=['POST'])
def webhook():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "OK", 200

@app.route('/')
def set_webhook():
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL + '/' + API_TOKEN, timeout=60)
    return "Webhook set", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)