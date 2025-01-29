import os
import logging
import queue
import gc
from threading import Thread
from urllib.parse import urlparse
import subprocess  # For running ffmpeg commands
from flask import Flask, request
import telebot
import yt_dlp

# ──────────────────── 🎯 CONFIGURATION ──────────────────── #

API_TOKEN = os.getenv('BOT_TOKEN')  # Telegram Bot API Token
WEBHOOK_URL = os.getenv('WEBHOOK_URL')  # Webhook URL for Flask
PORT = int(os.getenv('PORT', 8080))  # Default Flask port

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

# Task queue for handling multiple requests
task_queue = queue.Queue()

# ──────────────────── 🔗 URL VALIDATION ──────────────────── #

def is_valid_url(url):
    """Check if the provided URL is valid and belongs to a supported platform."""
    try:
        parsed_url = urlparse(url)
        return parsed_url.scheme in ['http', 'https'] and any(domain in parsed_url.netloc for domain in SUPPORTED_DOMAINS)
    except ValueError:
        return False

# ──────────────────── 🎥 FETCH VIDEO LINKS & THUMBNAIL ──────────────────── #

def get_video_data(url):
    """
    Extract the **direct streaming URL**, **original download page**, and **large thumbnail**.
    Uses yt-dlp to fetch metadata.
    """
    ydl_opts = {'format': 'best', 'noplaylist': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get('url'), info.get('webpage_url'), info.get('thumbnail')  # (Streaming URL, Download Page, Thumbnail)
    except Exception as e:
        logger.error(f"Error fetching video data: {e}")
        return None, None, None

# ──────────────────── 🎬 SCREENSHOT GENERATOR ──────────────────── #

def generate_screenshot(video_url, output_filename="screenshot.png"):
    """Generate a screenshot from the video at 30 seconds using ffmpeg."""
    try:
        command = [
            'ffmpeg', '-ss', '00:00:30', '-i', video_url, '-vframes', '1', '-q:v', '2', output_filename
        ]
        subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return output_filename
    except subprocess.CalledProcessError as e:
        logger.error(f"Error generating screenshot: {e}")
        return None

# ──────────────────── ⏳ 1-MINUTE TRIMMED VIDEO ──────────────────── #

def generate_trimmed_video(video_url, output_filename="trimmed_video.mp4"):
    """Generate a 1-minute trimmed version of the video."""
    try:
        command = [
            'ffmpeg', '-i', video_url, '-t', '00:01:00', '-c:v', 'libx264', '-c:a', 'aac', output_filename
        ]
        subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        return output_filename
    except subprocess.CalledProcessError as e:
        logger.error(f"Error trimming video: {e}")
        return None

# ──────────────────── 🔄 PROCESSING VIDEO REQUESTS ──────────────────── #

def handle_video_task(url, message):
    """Process a video request: fetch URLs, thumbnail & send response."""
    streaming_url, download_url, thumbnail_url = get_video_data(url)

    if not streaming_url or not download_url:
        bot.reply_to(message, "❌ Error: Unable to fetch video details.")
        return

    # If it's a video platform (Xvideos, Xnxx, etc.), show a large thumbnail
    if any(domain in url for domain in ['xvideos.com', 'xnxx.com', 'xhamster.com', 'pornhub.com']):
        bot.send_photo(
            chat_id=message.chat.id,
            photo=thumbnail_url,  # High-resolution thumbnail
            caption=f"🎥 <b>Watch Online:</b> <a href='{streaming_url}'>Click Here</a>\n"
                    f"💾 <b>Download Video:</b> <a href='{download_url}'>Click Here</a>",
            parse_mode="HTML"
        )
    else:
        # Generate screenshot and send it
        screenshot_filename = generate_screenshot(streaming_url)
        if screenshot_filename:
            bot.send_photo(
                chat_id=message.chat.id,
                photo=open(screenshot_filename, 'rb'),
                caption=f"📸 Screenshot from video. Watch Online: <a href='{streaming_url}'>Click Here</a>",
                parse_mode="HTML"
            )

        # Generate trimmed 1-minute video and send it
        trimmed_filename = generate_trimmed_video(streaming_url)
        if trimmed_filename:
            bot.send_video(
                chat_id=message.chat.id,
                video=open(trimmed_filename, 'rb'),
                caption="⏳ Here's a 1-minute trimmed version of the video.",
            )

# ──────────────────── ⚙️ BACKGROUND WORKER ──────────────────── #

def worker():
    """Worker thread that processes queued video tasks."""
    while True:
        task = task_queue.get()
        if task is None:
            break
        url, message = task
        handle_video_task(url, message)
        task_queue.task_done()

# Start worker threads for better performance
for _ in range(4):
    Thread(target=worker, daemon=True).start()

# ──────────────────── 🤖 BOT COMMANDS ──────────────────── #

@bot.message_handler(commands=['start'])
def start(message):
    """Welcome message for the bot."""
    bot.reply_to(message, "👋 Welcome! Send me a video link to **Watch Online**, **Download**, or get a **Screenshot**.")

@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_message(message):
    """Process incoming messages and validate URLs."""
    url = message.text.strip()

    if not is_valid_url(url):
        bot.reply_to(message, "❌ Invalid or unsupported URL.")
        return

    bot.reply_to(message, "⏳ Fetching video details. Please wait...")
    task_queue.put((url, message))

# ──────────────────── 🌐 FLASK SERVER ──────────────────── #

app = Flask(__name__)

@app.route('/' + API_TOKEN, methods=['POST'])
def webhook():
    """Process Telegram updates via webhook."""
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "OK", 200

@app.route('/')
def set_webhook():
    """Set up the Telegram bot webhook."""
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{API_TOKEN}", timeout=60)
    return "Webhook set", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)