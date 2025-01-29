import os
import logging
from flask import Flask, request
import telebot
import yt_dlp
import re
from urllib.parse import urlparse
from threading import Thread
import queue
import gc  # Memory cleanup

# Environment variables
API_TOKEN = os.getenv('BOT_TOKEN')  # Bot token
WEBHOOK_URL = os.getenv('WEBHOOK_URL')  # Webhook URL
PORT = int(os.getenv('PORT', 8080))  # Default to 8080
COOKIES_FILE = 'cookies.txt'

# Initialize the bot
bot = telebot.TeleBot(API_TOKEN, parse_mode='HTML')

# Logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Supported domains
SUPPORTED_DOMAINS = [
    'youtube.com', 'youtu.be', 'instagram.com', 'x.com',
    'facebook.com', 'xvideos.com', 'xnxx.com', 'xhamster.com', 'pornhub.com'
]

# Task queue
task_queue = queue.Queue()

# Validate URLs
def is_valid_url(url):
    try:
        result = urlparse(url)
        return result.scheme in ['http', 'https'] and any(domain in result.netloc for domain in SUPPORTED_DOMAINS)
    except ValueError:
        return False

# Fetch direct video file link
def get_direct_video_link(url):
    ydl_opts = {
        'format': 'best',
        'noplaylist': True,
        'quiet': True
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            direct_video_url = info_dict.get('url')  # Direct file link
            return direct_video_url
    except Exception as e:
        logger.error(f"Error fetching direct video link: {e}")
        return None

# Handle the direct download task
def handle_video_task(url, message):
    direct_link = get_direct_video_link(url)

    if not direct_link:
        bot.reply_to(message, "❌ Error: Unable to fetch the direct video link.")
        return

    # Send the **Chrome-compatible direct download link**
    bot.reply_to(
        message,
        f"🔽 **Click below to download directly**\n"
        f"👉 <a href='{direct_link}'>Download Video</a>\n\n"
        f"📌 *If the video doesn't download, long-press the link and select 'Download' in Chrome.*",
        parse_mode="HTML"
    )

# Worker function to process tasks
def worker():
    while True:
        task = task_queue.get()
        if task is None:
            break
        url, message = task
        handle_video_task(url, message)
        task_queue.task_done()

# Start worker threads
for _ in range(4):  # Adjust as needed
    Thread(target=worker, daemon=True).start()

# Command: /start
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "👋 Welcome! Send me a video link to **Download Directly in Chrome**.")

# Handle video requests
@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_message(message):
    url = message.text.strip()
    if not is_valid_url(url):
        bot.reply_to(message, "❌ Invalid or unsupported URL.")
        return

    bot.reply_to(message, "⏳ Fetching direct download link. Please wait...")
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
    return "Webhook set", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)