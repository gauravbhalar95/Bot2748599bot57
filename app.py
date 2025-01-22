import os
import logging
from flask import Flask, request
import telebot
import yt_dlp
import re
from urllib.parse import urlparse
import nest_asyncio

# Apply the patch for nested event loops
nest_asyncio.apply()

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

# Directories
DOWNLOAD_DIR = 'downloads'
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Supported domains
SUPPORTED_DOMAINS = [
    'youtube.com', 'youtu.be', 'instagram.com', 'x.com',
    'facebook.com', 'xvideos.com', 'xnxx.com', 'xhamster.com', 'pornhub.com'
]

# Utility to sanitize filenames
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

# Validate Instagram story URLs
def is_instagram_story_url(url):
    try:
        result = urlparse(url)
        return 'instagram.com/stories/' in result.path
    except ValueError:
        return False

# Download Instagram story using yt-dlp
def download_instagram_story(url):
    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'outtmpl': f'{DOWNLOAD_DIR}/{sanitize_filename("%(uploader)s_%(upload_date)s")}.%(ext)s',
        'cookiefile': COOKIES_FILE if os.path.exists(COOKIES_FILE) else None,
        'socket_timeout': 10,
        'retries': 5,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            return ydl.prepare_filename(info_dict), info_dict.get('filesize', 0)
    except Exception as e:
        logger.error(f"Error downloading Instagram story: {e}")
        return None, 0

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
            return ydl.prepare_filename(info_dict), info_dict.get('filesize', 0)
    except Exception as e:
        logger.error(f"Error downloading video: {e}")
        return None, 0

# Command: /start
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "Welcome! Send me a video link or Instagram story link to download.")

# Handle messages for video and Instagram story download
@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_message(message):
    url = message.text.strip()
    if not is_valid_url(url):
        bot.reply_to(message, "Invalid or unsupported URL.")
        return

    if is_instagram_story_url(url):
        bot.reply_to(message, "Downloading Instagram story, please wait...")
        file_path, file_size = download_instagram_story(url)
    else:
        bot.reply_to(message, "Downloading video, please wait...")
        file_path, file_size = download_video(url)

    if not file_path:
        bot.reply_to(message, "Error: Download failed. Ensure the URL is correct.")
        return

    try:
        # Check if the file size exceeds Telegram's limit (2GB)
        if file_size > 2 * 1024 * 1024 * 1024:  # 2GB in bytes
            bot.reply_to(
                message,
                f"The file is too large to send on Telegram. Try downloading it manually."
            )
        else:
            # Send the downloaded file
            with open(file_path, 'rb') as file:
                bot.send_document(message.chat.id, file)
    except Exception as e:
        logger.error(f"Error sending file: {e}")
        bot.reply_to(message, f"An error occurred: {e}")
    finally:
        # Clean up the file
        if os.path.exists(file_path):
            os.remove(file_path)

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