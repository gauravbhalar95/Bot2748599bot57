import os
import logging
from flask import Flask, request
import telebot
import yt_dlp
import re
from urllib.parse import urlparse
from threading import Thread
import queue
import gc  # Garbage collection

# Configurations
BOT_TOKEN = os.getenv('BOT_TOKEN')  # Telegram Bot Token
WEBHOOK_URL = os.getenv('WEBHOOK_URL')  # Webhook URL
PORT = int(os.getenv('PORT', 8080))  # Default Port
COOKIES_FILE = 'cookies.txt'

# Initialize the bot
bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML')

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Download directory
DOWNLOAD_DIR = 'downloads'
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Supported domains
SUPPORTED_DOMAINS = [
    'youtube.com', 'youtu.be', 'instagram.com', 'x.com',
    'facebook.com', 'xvideos.com', 'xnxx.com', 'xhamster.com', 'pornhub.com'
]

# Task queue for multi-threading
task_queue = queue.Queue()

# Sanitize filename to prevent errors
def sanitize_filename(filename, max_length=250):
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)
    return filename.strip()[:max_length]

# Validate URL
def is_valid_url(url):
    try:
        result = urlparse(url)
        return result.scheme in ['http', 'https'] and any(domain in result.netloc for domain in SUPPORTED_DOMAINS)
    except ValueError:
        return False

# Download video using yt-dlp
def download_video(url):
    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'outtmpl': f'{DOWNLOAD_DIR}/{sanitize_filename("%(title)s")}.%(ext)s',
        'cookiefile': COOKIES_FILE if os.path.exists(COOKIES_FILE) else None,
        'socket_timeout': 10,
        'retries': 5,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info_dict)
            file_size = info_dict.get('filesize', 0)
            return file_path, file_size
    except Exception as e:
        logger.error(f"Download Error: {e}")
        return None, 0

# Get streaming link
def get_streaming_url(url):
    try:
        with yt_dlp.YoutubeDL({'format': 'best', 'noplaylist': True}) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            return info_dict.get('url')
    except Exception as e:
        logger.error(f"Streaming Link Error: {e}")
        return None

# Process video download
def process_download(url, message):
    file_path, file_size = download_video(url)

    if not file_path:
        bot.reply_to(message, "❌ Download failed. Invalid URL or restricted video.")
        return

    try:
        # If file is larger than 2GB, send streaming and direct link
        if file_size > 2 * 1024 * 1024 * 1024:  # 2GB
            streaming_url = get_streaming_url(url)
            if streaming_url:
                bot.reply_to(
                    message,
                    f"⚠️ Video too large to send on Telegram.\n\n"
                    f"🎥 **Stream:** [Click Here]({streaming_url})\n"
                    f"⬇️ **Download:** [Click Here]({url})",
                    parse_mode="Markdown"
                )
            else:
                bot.reply_to(message, "❌ Unable to fetch streaming link. Try downloading manually.")
        else:
            # Send video directly
            with open(file_path, 'rb') as video:
                bot.send_video(message.chat.id, video)

    except Exception as e:
        logger.error(f"Sending Error: {e}")
        bot.reply_to(message, f"❌ Error: {e}")
    finally:
        # Cleanup
        if os.path.exists(file_path):
            os.remove(file_path)
        gc.collect()

# Worker function for multi-threading
def worker():
    while True:
        task = task_queue.get()
        if task is None:
            break
        url, message = task
        process_download(url, message)
        task_queue.task_done()

# Start worker threads
for _ in range(4):  # Adjust number of threads as needed
    Thread(target=worker, daemon=True).start()

# Command: /start
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(
        message,
        "👋 Welcome! Send me a video link to download or stream.\n\n"
        "🎥 **Supported platforms:** YouTube, Instagram, Facebook, X (Twitter), and adult sites.\n\n"
        "⚠️ If the file is larger than 2GB, I'll provide a streaming and download link."
    )

# Handle messages (video download requests)
@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_message(message):
    url = message.text.strip()
    if not is_valid_url(url):
        bot.reply_to(message, "❌ Invalid or unsupported URL.")
        return

    bot.reply_to(message, "⏳ Processing your request. Please wait...")
    task_queue.put((url, message))

# Flask app for webhook
app = Flask(__name__)

@app.route('/' + BOT_TOKEN, methods=['POST'])
def webhook():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "OK", 200

@app.route('/')
def set_webhook():
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL + '/' + BOT_TOKEN, timeout=60)
    return "Webhook set", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)