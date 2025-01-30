import os
import logging
import queue
import gc
import re
from threading import Thread
from urllib.parse import urlparse
from flask import Flask, request
import telebot
import yt_dlp
import ffmpeg  

# ──────────────────── 🎯 CONFIGURATION ──────────────────── #

API_TOKEN = os.getenv('BOT_TOKEN')  
WEBHOOK_URL = os.getenv('WEBHOOK_URL')  
PORT = int(os.getenv('PORT', 8080))  
COOKIES_FILE = 'cookies.txt'
DOWNLOAD_DIR = 'downloads'
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Initialize the bot
bot = telebot.TeleBot(API_TOKEN, parse_mode='HTML')

# Logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Supported video platforms
SUPPORTED_DOMAINS = [
    'youtube.com', 'youtu.be', 'instagram.com', 'x.com',
    'facebook.com', 'xvideos.com', 'xnxx.com', 'xhamster.com', 'pornhub.com'
]

# Task queue
task_queue = queue.Queue()

# ──────────────────── 🔗 URL VALIDATION ──────────────────── #

def is_valid_url(url):
    try:
        parsed_url = urlparse(url)
        return parsed_url.scheme in ['http', 'https'] and any(domain in parsed_url.netloc for domain in SUPPORTED_DOMAINS)
    except ValueError:
        return False

# ──────────────────── 🎥 VIDEO DOWNLOAD & TRIM ──────────────────── #

def sanitize_filename(filename, max_length=250):
    return re.sub(r'[\\/*?:"<>|]', "", filename.strip()[:max_length])

def download_video(url):
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]',
        'outtmpl': f'{DOWNLOAD_DIR}/{sanitize_filename("%(title)s")}.%(ext)s',
        'cookiefile': COOKIES_FILE if os.path.exists(COOKIES_FILE) else None,
        'socket_timeout': 10,
        'retries': 5,
        'postprocessors': [{'key': 'FFmpegMetadata'}],  
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info_dict)
            return file_path, info_dict.get('filesize', 0)
    except Exception as e:
        logger.error(f"Error downloading video: {e}")
        return None, 0

def trim_video(input_file, output_file, start_time, end_time):
    try:
        (
            ffmpeg
            .input(input_file, ss=start_time, to=end_time)
            .output(output_file, format='mp4', codec='copy')
            .run(overwrite_output=True)
        )
        return output_file
    except Exception as e:
        logger.error(f"Error trimming video: {e}")
        return None

# ──────────────────── 🔄 PROCESSING VIDEO REQUESTS ──────────────────── #

def handle_video_task(url, message, start_time=None, end_time=None):
    file_path, file_size = download_video(url)

    if not file_path:
        bot.reply_to(message, "❌ Error: Unable to download the video.")
        return

    try:
        if start_time and end_time:
            trimmed_file = f"{DOWNLOAD_DIR}/trimmed_{os.path.basename(file_path)}"
            trimmed_file = trim_video(file_path, trimmed_file, start_time, end_time)
            if trimmed_file:
                file_path = trimmed_file

        if file_size > 50 * 1024 * 1024:
            bot.reply_to(message, "⚠️ The file is too large for Telegram. Try trimming it first.")
        else:
            with open(file_path, 'rb') as video:
                bot.send_video(message.chat.id, video)

    except Exception as e:
        logger.error(f"Error sending video: {e}")
        bot.reply_to(message, f"❌ Error: {e}")

    finally:
        if os.path.exists(file_path):
            os.remove(file_path)
        gc.collect()

# ──────────────────── ⚙️ BACKGROUND WORKER ──────────────────── #

def worker():
    while True:
        task = task_queue.get()
        if task is None:
            break
        url, message, start_time, end_time = task
        handle_video_task(url, message, start_time, end_time)
        task_queue.task_done()

for _ in range(4):
    Thread(target=worker, daemon=True).start()

# ──────────────────── 🤖 BOT COMMANDS ──────────────────── #

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(
        message,
        "👋 Welcome! Send me a video link to **Download or Trim**.\n\n"
        "To trim a video, use:\n"
        "<code>/trim &lt;URL&gt; &lt;start_time&gt; &lt;end_time&gt;</code>\n"
        "Example: <code>/trim https://youtu.be/example 00:01:30 00:03:00</code>",
        parse_mode="HTML"
    )

@bot.message_handler(commands=['trim'])
def trim_command(message):
    try:
        args = message.text.split()
        if len(args) != 4:
            bot.reply_to(message, "⚠️ Usage: /trim <URL> <start_time> <end_time>")
            return

        url, start_time, end_time = args[1], args[2], args[3]

        if not is_valid_url(url):
            bot.reply_to(message, "❌ Invalid or unsupported URL.")
            return

        bot.reply_to(message, "⏳ Processing your request. Please wait...")
        task_queue.put((url, message, start_time, end_time))

    except Exception as e:
        bot.reply_to(message, f"❌ Error: {e}")

@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_message(message):
    url = message.text.strip()

    if not is_valid_url(url):
        bot.reply_to(message, "❌ Invalid or unsupported URL.")
        return

    bot.reply_to(message, "⏳ Fetching video details. Please wait...")
    task_queue.put((url, message, None, None))

# ──────────────────── 🌐 FLASK SERVER ──────────────────── #

app = Flask(__name__)

@app.route('/' + API_TOKEN, methods=['POST'])
def webhook():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "OK", 200

@app.route('/')
def set_webhook():
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{API_TOKEN}", timeout=60)
    return "Webhook set", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)