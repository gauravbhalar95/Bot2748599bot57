import os
import logging
import gc  # Memory cleanup
import queue
from flask import Flask, request
from urllib.parse import urlparse
from threading import Thread
import telebot
import yt_dlp
import re

# ---------------------------[ Environment Variables ]---------------------------
API_TOKEN = os.getenv('BOT_TOKEN')  # Telegram bot token
WEBHOOK_URL = os.getenv('WEBHOOK_URL')  # Webhook URL
PORT = int(os.getenv('PORT', 8080))  # Default port
COOKIES_FILE = 'cookies.txt'  # Cookies file for authenticated downloads

# ---------------------------[ Initialize Bot & Logging ]---------------------------
bot = telebot.TeleBot(API_TOKEN, parse_mode='HTML')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------[ Directories & Constants ]---------------------------
DOWNLOAD_DIR = 'downloads'
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

SUPPORTED_DOMAINS = [
    'youtube.com', 'youtu.be', 'instagram.com', 'x.com',
    'facebook.com', 'xvideos.com', 'xnxx.com', 'xhamster.com', 'pornhub.com'
]

task_queue = queue.Queue()  # Queue for handling multiple downloads

# ---------------------------[ Utility Functions ]---------------------------
def sanitize_filename(filename, max_length=250):
    """Sanitize filenames to prevent illegal characters."""
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)
    return filename.strip()[:max_length]

def is_valid_url(url):
    """Check if the given URL is valid and supported."""
    try:
        result = urlparse(url)
        return result.scheme in ['http', 'https'] and any(domain in result.netloc for domain in SUPPORTED_DOMAINS)
    except ValueError:
        return False

# ---------------------------[ Download & Streaming Functions ]---------------------------
def download_video(url):
    """Download video using yt-dlp and return file path & size."""
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

def get_streaming_url(url):
    """Fetch streaming URL for the given video."""
    ydl_opts = {'format': 'best', 'noplaylist': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            return info_dict.get('url')
    except Exception as e:
        logger.error(f"Error fetching streaming URL: {e}")
        return None

# ---------------------------[ Task Handling ]---------------------------
def handle_download_task(url, message):
    """Process the video download task and send response to user."""
    file_path, file_size = download_video(url)

    if not file_path:
        bot.reply_to(message, "❌ Error: Video download failed. Please check the URL.")
        return

    try:
        if file_size > 2 * 1024 * 1024 * 1024:  # If file size exceeds 2GB
            streaming_url = get_streaming_url(url)
            if streaming_url:
                bot.reply_to(
                    message,
                    f"⚠️ The video is too large to send on Telegram.\n\n"
                    f"🎥 **Streaming Link:** [Click Here]({streaming_url})\n"
                    f"⬇️ **Download Link:** [Click Here]({url})",
                    parse_mode="Markdown"
                )
            else:
                bot.reply_to(message, "❌ Unable to fetch a streaming link. Try downloading manually.")
        else:
            with open(file_path, 'rb') as video:
                bot.send_video(message.chat.id, video)
    except Exception as e:
        logger.error(f"Error sending video: {e}")
        streaming_url = get_streaming_url(url)
        if streaming_url:
            bot.reply_to(
                message,
                f"⚠️ The video is too large to send directly on Telegram.\n\n"
                f"🎥 **Streaming Link:** [Click Here]({streaming_url})",
                parse_mode="Markdown"
            )
        else:
            bot.reply_to(message, f"❌ Error: {e}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)  # Delete downloaded file
        gc.collect()  # Free memory

# ---------------------------[ Worker Thread ]---------------------------
def worker():
    """Worker thread to process download tasks from the queue."""
    while True:
        task = task_queue.get()
        if task is None:
            break
        url, message = task
        handle_download_task(url, message)
        task_queue.task_done()

# Start worker threads
for _ in range(4):  # Adjust as needed
    Thread(target=worker, daemon=True).start()

# ---------------------------[ Telegram Bot Handlers ]---------------------------
@bot.message_handler(commands=['start'])
def start(message):
    """Handle /start command."""
    bot.reply_to(
        message,
        "👋 Welcome! Send me a video link to download or stream.\n\n"
        "🎥 **Supported Platforms:**\n"
        "✔️ YouTube\n✔️ Instagram\n✔️ Facebook\n✔️ Twitter (X)\n✔️ Adult sites\n\n"
        "⚠️ If the file is larger than **2GB**, I will provide a **streaming link** instead."
    )

@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_message(message):
    """Handle text messages containing video URLs."""
    url = message.text.strip()
    if not is_valid_url(url):
        bot.reply_to(message, "❌ Invalid or unsupported URL.")
        return

    bot.reply_to(message, "⏳ Processing your request. Please wait...")
    task_queue.put((url, message))

# ---------------------------[ Flask Webhook Server ]---------------------------
app = Flask(__name__)

@app.route('/' + API_TOKEN, methods=['POST'])
def webhook():
    """Process webhook requests from Telegram."""
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "OK", 200

@app.route('/')
def set_webhook():
    """Set webhook for Telegram bot."""
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL + '/' + API_TOKEN, timeout=60)
    return "Webhook set", 200

# ---------------------------[ Run Flask Server ]---------------------------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)