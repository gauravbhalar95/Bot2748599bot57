import os
import logging
from flask import Flask, request, send_from_directory
import telebot
import yt_dlp
import re
from urllib.parse import urlparse
from threading import Thread
import queue
import gc  # Memory cleanup

# Environment Variables
API_TOKEN = os.getenv('BOT_TOKEN')  # Telegram Bot Token
WEBHOOK_URL = os.getenv('WEBHOOK_URL')  # Public Webhook URL
PORT = int(os.getenv('PORT', 8080))  # Default Port
COOKIES_FILE = 'cookies.txt'

# Initialize Bot
bot = telebot.TeleBot(API_TOKEN, parse_mode='HTML')

# Logging Configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Directories
DOWNLOAD_DIR = 'downloads'
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Supported Domains
SUPPORTED_DOMAINS = [
    'youtube.com', 'youtu.be', 'instagram.com', 'x.com',
    'facebook.com', 'xvideos.com', 'xnxx.com', 'xhamster.com', 'pornhub.com'
]

# Task Queue
task_queue = queue.Queue()

# Sanitize Filenames
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

# Download Video
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

# Fetch Streaming URL
def get_streaming_url(url):
    ydl_opts = {'format': 'best', 'noplaylist': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            return info_dict.get('url')
    except Exception as e:
        logger.error(f"Error fetching streaming URL: {e}")
        return None

# Handle Video Download Task
def handle_download_task(url, message):
    file_path, file_size = download_video(url)

    if not file_path:
        bot.reply_to(message, "❌ Error: Video download failed. Ensure the URL is correct.")
        return

    try:
        if file_size > 2 * 1024 * 1024 * 1024:  # Telegram's 2GB limit
            streaming_url = get_streaming_url(url)
            download_link = f"{WEBHOOK_URL}/download/{os.path.basename(file_path)}"

            reply_text = "⚠️ The video is too large for Telegram.\n\n"
            if streaming_url:
                reply_text += f"🎥 **Watch Online:** [Click Here]({streaming_url})\n"
            reply_text += f"⬇️ **Download Video:** [Click Here]({download_link})"

            bot.reply_to(message, reply_text, parse_mode="Markdown")
        else:
            with open(file_path, 'rb') as video:
                bot.send_video(message.chat.id, video)
    except Exception as e:
        logger.error(f"Error sending video: {e}")
        streaming_url = get_streaming_url(url)
        download_link = f"{WEBHOOK_URL}/download/{os.path.basename(file_path)}"

        reply_text = "⚠️ The video is too large for Telegram.\n\n"
        if streaming_url:
            reply_text += f"🎥 **Watch Online:** [Click Here]({streaming_url})\n"
        reply_text += f"⬇️ **Download Video:** [Click Here]({download_link})"

        bot.reply_to(message, reply_text, parse_mode="Markdown")
    finally:
        gc.collect()

# Worker Function
def worker():
    while True:
        task = task_queue.get()
        if task is None:
            break
        url, message = task
        handle_download_task(url, message)
        task_queue.task_done()

# Start Worker Threads
for _ in range(4):
    Thread(target=worker, daemon=True).start()

# Command: /start
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "👋 Welcome! Send me a video link to **Download** or **Watch Online**.")

# Handle Video Requests
@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_message(message):
    url = message.text.strip()
    if not is_valid_url(url):
        bot.reply_to(message, "❌ Invalid or unsupported URL.")
        return

    bot.reply_to(message, "⏳ Fetching video, please wait...")
    task_queue.put((url, message))

# Flask App for Webhook
app = Flask(__name__)

@app.route('/' + API_TOKEN, methods=['POST'])
def webhook():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "OK", 200

# Serve Download Links
@app.route('/download/<filename>')
def serve_download(filename):
    return send_from_directory(DOWNLOAD_DIR, filename, as_attachment=True)

@app.route('/')
def set_webhook():
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL + '/' + API_TOKEN, timeout=60)
    return "Webhook set", 200

# Run Flask App
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)