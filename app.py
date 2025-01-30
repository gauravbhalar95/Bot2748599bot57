import os
import logging
import psutil  # To monitor memory usage
from flask import Flask, request
import telebot
import yt_dlp
from urllib.parse import urlparse
from threading import Thread
import queue
import gc

# Environment variables
API_TOKEN = os.getenv('BOT_TOKEN')  # Telegram Bot Token
WEBHOOK_URL = os.getenv('WEBHOOK_URL')  # Webhook URL for hosting
PORT = int(os.getenv('PORT', 8080))  # Default port

# Initialize bot
bot = telebot.TeleBot(API_TOKEN, parse_mode='Markdown')

# Logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Supported domains
SUPPORTED_DOMAINS = [
    'youtube.com', 'youtu.be', 'instagram.com', 'x.com',
    'facebook.com', 'xvideos.com', 'xnxx.com', 'xhamster.com', 'pornhub.com'
]

# Task queue for multi-threading
task_queue = queue.Queue()

# Check if URL is valid
def is_valid_url(url):
    try:
        result = urlparse(url)
        return result.scheme in ['http', 'https'] and any(domain in result.netloc for domain in SUPPORTED_DOMAINS)
    except ValueError:
        return False

# Check current memory usage
def is_memory_high(threshold=80):
    memory_usage = psutil.virtual_memory().percent
    return memory_usage > threshold

# Fetch streaming URL without downloading
def get_streaming_url(url):
    ydl_opts = {'format': 'best', 'noplaylist': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            return info_dict.get('url')
    except Exception as e:
        logger.error(f"Error fetching streaming URL: {e}")
        return None

# Download media using yt-dlp
def download_media(url, output_dir='downloads/'):
    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'outtmpl': f'{output_dir}%(title)s.%(ext)s',
        'retries': 5,
        'noplaylist': True
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info_dict)
        return file_path
    except Exception as e:
        logger.error(f"Error downloading media: {e}")
        return None

# Handle video requests
def handle_request(url, message):
    if not is_valid_url(url):
        bot.reply_to(message, "Invalid or unsupported URL. Supported platforms: YouTube, Instagram, Twitter, Facebook.")
        return

    if is_memory_high():
        streaming_url = get_streaming_url(url)
        if streaming_url:
            bot.reply_to(
                message,
                f"⚠️ **Memory usage is too high.**\n\n"
                f"🎥 **Stream Here:** [Click Here]({streaming_url})\n"
                f"⬇️ **Download Here:** [Click Here]({url})",
                parse_mode="Markdown"
            )
        else:
            bot.reply_to(message, f"⚠️ **High memory usage detected. Try downloading manually:** [Download Here]({url})")
        return

    try:
        bot.reply_to(message, "Downloading video, please wait...")
        file_path = download_media(url)

        if file_path:
            with open(file_path, 'rb') as video:
                bot.send_video(message.chat.id, video)
            os.remove(file_path)  # Clean up after sending
            gc.collect()  # Run garbage collection to free memory
        else:
            bot.reply_to(message, "Failed to download the video.")
    except Exception as e:
        logger.error(f"Error handling the video request: {e}")
        bot.reply_to(message, "An error occurred while processing your request.")

# Flask app for webhook
app = Flask(__name__)

@app.route('/' + API_TOKEN, methods=['POST'])
def bot_webhook():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "!", 200


@app.route('/')
def set_webhook():
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL + '/' + API_TOKEN, timeout=60)
    return "Webhook set", 200


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=PORT, debug=True)