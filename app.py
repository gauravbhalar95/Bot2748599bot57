import os
import logging
import queue
import gc
import re
import requests
from threading import Thread
from urllib.parse import urlparse
from flask import Flask, request
import telebot
import yt_dlp
import ffmpeg  

# ──────────────────── 🎯 CONFIGURATION ──────────────────── #

API_TOKEN = os.getenv('BOT_TOKEN')  # Telegram Bot API Token
WEBHOOK_URL = os.getenv('WEBHOOK_URL')  # Webhook URL for Flask
PORT = int(os.getenv('PORT', 8080))  # Default Flask port
COOKIES_FILE = 'cookies.txt'
DOWNLOAD_DIR = 'downloads'
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

bot = telebot.TeleBot(API_TOKEN, parse_mode='HTML')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SUPPORTED_DOMAINS = [
    'youtube.com', 'youtu.be', 'instagram.com', 'x.com',
    'facebook.com', 'xvideos.com', 'xnxx.com', 'xhamster.com', 'pornhub.com'
]

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
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)
    return filename.strip()[:max_length]

def download_video(url):
    """Download video from YouTube, Twitter, or other sources."""
    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'outtmpl': f'{DOWNLOAD_DIR}/{sanitize_filename("%(title)s")}.%(ext)s',
        'merge_output_format': 'mp4',
        'socket_timeout': 10,
        'retries': 5,
        'quiet': False
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info_dict)
            return file_path, info_dict.get('filesize', 0)
    except Exception as e:
        logger.error(f"Error downloading video: {e}")
        return None, 0

def download_twitter_video(url):
    """Download Twitter video."""
    try:
        response = requests.get(url, stream=True)
        filename = f"{DOWNLOAD_DIR}/twitter_video.mp4"
        with open(filename, "wb") as video_file:
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    video_file.write(chunk)
        return filename
    except Exception as e:
        logger.error(f"Error downloading Twitter video: {e}")
        return None

def trim_video(input_file, output_file, start_time, end_time):
    """Trim a video between start_time and end_time using FFmpeg."""
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
    """Process a video request: Download, Trim (optional), and Send."""
    
    if "twitter.com" in url or "x.com" in url:
        file_path = download_twitter_video(url)
    else:
        file_path, file_size = download_video(url)

    if not file_path:
        bot.reply_to(message, "❌ Error: Unable to download the video.")
        return

    try:
        # If trimming is requested
        if start_time and end_time:
            trimmed_file = f"{DOWNLOAD_DIR}/trimmed_{os.path.basename(file_path)}"
            trimmed_file = trim_video(file_path, trimmed_file, start_time, end_time)
            if trimmed_file:
                file_path = trimmed_file

        # Check Telegram file size limit (50MB for bots, 2GB for premium users)
        if os.path.getsize(file_path) > 50 * 1024 * 1024:
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
    """Worker thread that processes queued video tasks."""
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
        "To trim a video, use the format:\n"
        "<code>/trim &lt;URL&gt; &lt;start_time&gt; &lt;end_time&gt;</code>\n"
        "Example: <code>/trim https://youtu.be/example 00:01:30 00:03:00</code>",
        parse_mode="HTML"
    )

@bot.message_handler(commands=['trim'])
def trim_command(message):
    try:
        args = message.text.split()
        if len(args) != 4:
            bot.reply_to(message, "⚠️ Usage: /trim <URL> <start_time> <end_time>\nExample: /trim https://youtu.be/example 00:00:30 00:01:30")
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