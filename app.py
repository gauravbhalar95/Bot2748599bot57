import os
import logging
from flask import Flask, request
import telebot
import yt_dlp
import re
from urllib.parse import urlparse
from threading import Thread
import queue
import gc

# Environment variables
API_TOKEN = os.getenv('BOT_TOKEN')  # Bot token from environment
WEBHOOK_URL = os.getenv('WEBHOOK_URL')  # Webhook URL
PORT = int(os.getenv('PORT', 8080))  # Default to 8080
COOKIES_FILE = 'cookies.txt'

# Initialize bot
bot = telebot.TeleBot(API_TOKEN, parse_mode='Markdown')

# Logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Directories
DOWNLOAD_DIR = 'downloads'
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Supported domains
SUPPORTED_DOMAINS = [
    'youtube.com', 'youtu.be', 'instagram.com', 'x.com',
    'facebook.com', 'xvideos.com', 'xnxx.com', 'xhamster.com', 'pornhub.com'
]

# Task queue for multi-threading
task_queue = queue.Queue()

# Sanitize filenames
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
        logger.error(f"Error downloading video: {e}")
        return None, 0

# Fetch streaming URL
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

# Handle video download task
def handle_download_task(url, message):
    file_path, file_size = download_video(url)

    if not file_path:
        bot.reply_to(message, "❌ **Error:** Video download failed. Ensure the URL is correct.")
        return

    try:
        if file_size > 2 * 1024 * 1024 * 1024:  # If file is larger than 2GB
            streaming_url = get_streaming_url(url)
            if streaming_url:
                bot.reply_to(
                    message,
                    f"⚠️ **Video too large to send on Telegram.**\n\n"
                    f"🎥 **Stream Here:** [Click Here]({streaming_url})\n"
                    f"⬇️ **Download Here:** [Click Here]({url})",
                    parse_mode="Markdown"
                )
            else:
                bot.reply_to(message, "❌ Unable to fetch streaming link. Try downloading manually.")
        else:
            with open(file_path, 'rb') as video:
                bot.send_video(message.chat.id, video)
    except Exception as e:
        logger.error(f"Error sending video: {e}")
        streaming_url = get_streaming_url(url)
        if streaming_url:
            bot.reply_to(
                message,
                f"⚠️ **Video too large to send directly on Telegram.**\n"
                f"🎥 **Stream Here:** [Click Here]({streaming_url})",
                parse_mode="Markdown"
            )
        else:
            bot.reply_to(message, f"❌ **Error:** {e}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)
        gc.collect()

# Worker function for processing downloads
def worker():
    while True:
        task = task_queue.get()
        if task is None:
            break
        url, message = task
        handle_download_task(url, message)
        task_queue.task_done()

# Start worker threads (adjust thread count for speed optimization)
for _ in range(4):
    Thread(target=worker, daemon=True).start()

# Command: /start
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "👋 **Welcome!**\nSend me a video link to **download** or **stream**.")

# Handle video downloads
@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_message(message):
    url = message.text.strip()
    if not is_valid_url(url):
        bot.reply_to(message, "❌ **Invalid or unsupported URL.**")
        return

    bot.reply_to(message, "⏳ **Processing your request...** Please wait.")
    task_queue.put((url, message))

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
    return "✅ Webhook set", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)