import os
import logging
from flask import Flask, request
import telebot
import yt_dlp
import re
import subprocess
from urllib.parse import urlparse, parse_qs
from mega import Mega
import time
import json
import instaloader  # Add instaloader for Instagram functionality

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


# Function to download Instagram profile posts
def download_instagram_profile(profile_url):
    loader = instaloader.Instaloader()
    username = profile_url.rstrip('/').split('/')[-1]

    try:
        # Download all posts to the output directory
        loader.download_profile(username, profile_pic=True, profile_pic_only=False, fast_update=True)
        return f"All posts from {username} downloaded successfully!"
    except Exception as e:
        logging.error("Error downloading Instagram profile", exc_info=True)
        raise


# Handle Instagram profile command
@bot2.message_handler(commands=['instagram'])
def handle_instagram_profile(message):
    args = message.text.split(maxsplit=1)
    if len(args) != 2:
        bot2.reply_to(message, "Usage: /instagram <Instagram Profile URL>")
        return

    profile_url = args[1]
    if not profile_url.startswith("https://www.instagram.com/"):
        bot2.reply_to(message, "Please provide a valid Instagram profile URL.")
        return

    try:
        bot2.reply_to(message, "Downloading Instagram profile posts, please wait...")
        result = download_instagram_profile(profile_url)
        bot2.reply_to(message, result)
    except Exception as e:
        bot2.reply_to(message, f"Failed to download Instagram profile: {str(e)}")


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