import os
import logging
from flask import Flask, request
import telebot
import yt_dlp
import re
from urllib.parse import urlparse, parse_qs
from mega import Mega
import time

# Load environment variables
API_TOKEN_2 = os.getenv('API_TOKEN_2')
CHANNEL_ID = os.getenv('CHANNEL_ID')  # Example: '@YourChannel'
KOYEB_URL = os.getenv('KOYEB_URL')  # Koyeb URL for webhook

# Initialize bot
bot2 = telebot.TeleBot(API_TOKEN_2, parse_mode='HTML')

# Directories
output_dir = 'downloads/'
cookies_file = 'cookies.txt'

# Ensure downloads directory exists
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# Logging configuration
logging.basicConfig(level=logging.DEBUG)

# Supported domains
SUPPORTED_DOMAINS = ['youtube.com', 'youtu.be', 'instagram.com', 'x.com', 'facebook.com']

# Mega client
mega_client = None


# Sanitize filenames for downloaded files
def sanitize_filename(filename, max_length=250):
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)
    return filename.strip()[:max_length]


# Check if a URL is valid and supported
def is_valid_url(url):
    try:
        result = urlparse(url)
        return result.scheme in ['http', 'https'] and any(domain in result.netloc for domain in SUPPORTED_DOMAINS)
    except ValueError:
        return False


# Download media function
def download_media(url, ydl_opts):
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info_dict)
        return file_path
    except Exception as e:
        logging.error("yt-dlp download error", exc_info=True)
        raise


# Handle Instagram-specific downloads automatically
@bot2.message_handler(func=lambda message: 'instagram.com' in message.text.lower(), content_types=['text'])
def handle_instagram_auto(message):
    url = message.text.strip()

    # Validate the Instagram URL
    if not url.startswith("https://www.instagram.com/"):
        bot2.reply_to(message, "Invalid Instagram URL. Please provide a valid Instagram post or reel link.")
        return

    try:
        bot2.reply_to(message, "Downloading from Instagram, please wait...")

        # Configure yt-dlp options
        ydl_opts = {
            'format': 'best[ext=mp4]/best',
            'outtmpl': f'{output_dir}{sanitize_filename("%(title)s")}.%(ext)s',
            'cookiefile': cookies_file,
            'username': os.getenv('INSTAGRAM_USERNAME'),
            'password': os.getenv('INSTAGRAM_PASSWORD'),
            'socket_timeout': 10,
            'retries': 5,
        }

        # Download Instagram media
        file_path = download_media(url, ydl_opts)

        # Send the downloaded video or image to the user
        with open(file_path, 'rb') as media:
            if file_path.endswith('.mp4'):
                bot2.send_video(message.chat.id, media)
            else:
                bot2.send_photo(message.chat.id, media)

        # Cleanup
        os.remove(file_path)

    except Exception as e:
        logging.error("Error downloading Instagram media", exc_info=True)
        bot2.reply_to(message, f"An error occurred while downloading: {str(e)}")


# Flask app for webhook
app = Flask(__name__)

@app.route('/' + API_TOKEN_2, methods=['POST'])
def bot_webhook():
    bot2.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "!", 200


@app.route('/')
def set_webhook():
    bot2.remove_webhook()
    bot2.set_webhook(url=KOYEB_URL + '/' + API_TOKEN_2, timeout=60)
    return "Webhook set", 200


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080, debug=True)