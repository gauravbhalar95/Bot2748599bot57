import os
import logging
import psutil
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

# Process video request
def handle_request(url, message):
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

    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'outtmpl': 'video.%(ext)s',
        'retries': 5,
        'noplaylist': True
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info_dict)
            file_size = info_dict.get('filesize', 0)

        if file_size > 2 * 1024 * 1024 * 1024:  # Check if file size is over 2GB
            streaming_url = get_streaming_url(url)
            bot.reply_to(
                message,
                f"⚠️ **Video is too large.**\n\n"
                f"🎥 **Stream Here:** [Click Here]({streaming_url})\n"
                f"⬇️ **Download Here:** [Click Here]({url})",
                parse_mode="Markdown"
            )
        else:
            with open(file_path, 'rb') as video:
                bot.send_video(message.chat.id, video)

        os.remove(file_path)
        gc.collect()

    except Exception as e:
        logger.error(f"Error processing request: {e}")
        streaming_url = get_streaming_url(url)
        bot.reply_to(
            message,
            f"⚠️ **Something went wrong.**\n\n"
            f"🎥 **Stream Here:** [Click Here]({streaming_url})\n"
            f"⬇️ **Download Here:** [Click Here]({url})",
            parse_mode="Markdown"
        )


@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_text_message(message):
    url = message.text.strip()
    if is_valid_url(url):
        handle_request(url, message)
    else:
        bot.reply_to(message, "Please provide a valid URL to download the video.")


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