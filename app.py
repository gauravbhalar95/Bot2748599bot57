import os
import logging
from flask import Flask, request
import telebot
import yt_dlp
from urllib.parse import urlparse
from mega import Mega
import re
import requests

# Environment Variables
API_TOKEN_2 = os.getenv('API_TOKEN_2')  # Your bot's API token
KOYEB_URL = os.getenv('KOYEB_URL')  # Your Koyeb webhook URL
output_dir = 'downloads/'
cookies_file = 'cookies.txt'
SUPPORTED_DOMAINS = ['instagram.com', 'youtube.com', 'youtu.be', 'x.com', 'facebook.com']

# Initialize bot and Flask app
bot2 = telebot.TeleBot(API_TOKEN_2, parse_mode='HTML')
app = Flask(__name__)

# Logging setup
logging.basicConfig(level=logging.DEBUG)

# Ensure output directory exists
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# Mega.nz client
mega_client = None

# Helper Functions
def sanitize_filename(filename, max_length=250):
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)
    return filename.strip()[:max_length]

def is_valid_url(url):
    try:
        result = urlparse(url)
        return result.scheme in ['http', 'https'] and any(domain in result.netloc for domain in SUPPORTED_DOMAINS)
    except ValueError:
        return False

def download_media(url):
    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'outtmpl': f'{output_dir}{sanitize_filename("%(title)s")}.%(ext)s',
        'cookiefile': cookies_file,
        'socket_timeout': 10,
        'retries': 5,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            return ydl.prepare_filename(info_dict)
    except Exception as e:
        logging.error("yt-dlp download error", exc_info=True)
        raise

def download_instagram_profile(url):
    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'outtmpl': f'{output_dir}%(uploader)s/%(title)s.%(ext)s',
        'cookiefile': cookies_file,
        'socket_timeout': 10,
        'retries': 5,
        'extract_flat': True,  # Extracts all links
    }
    downloaded_files = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            if '_type' in info_dict and info_dict['_type'] == 'playlist':
                for entry in info_dict['entries']:
                    file_path = download_media(entry['url'])
                    downloaded_files.append(file_path)
        return downloaded_files
    except Exception as e:
        logging.error("Instagram profile download error", exc_info=True)
        raise

def upload_to_mega(file_path):
    global mega_client
    if mega_client is None:
        raise Exception("Mega client is not logged in. Use /meganz <username> <password> to log in.")
    try:
        file = mega_client.upload(file_path)
        return mega_client.get_upload_link(file)
    except Exception as e:
        logging.error("Mega.nz upload error", exc_info=True)
        raise

# Bot Handlers
@bot2.message_handler(commands=['start'])
def handle_start(message):
    bot2.reply_to(message, "Welcome! Send me a supported URL (Instagram, YouTube, etc.) to download, or an Instagram profile URL to download all posts.")

@bot2.message_handler(commands=['meganz'])
def handle_mega_login(message):
    global mega_client
    args = message.text.split(maxsplit=2)
    if len(args) == 1:
        mega_client = Mega().login()  # Anonymous login
        bot2.reply_to(message, "Logged in to Mega.nz anonymously!")
    elif len(args) == 3:
        email, password = args[1], args[2]
        try:
            mega_client = Mega().login(email, password)
            bot2.reply_to(message, "Successfully logged in to Mega.nz!")
        except Exception as e:
            bot2.reply_to(message, f"Login failed: {str(e)}")
    else:
        bot2.reply_to(message, "Usage: /meganz <username> <password>")

@bot2.message_handler(func=lambda message: True, content_types=['text'])
def handle_message(message):
    url = message.text.strip()
    if is_valid_url(url):
        bot2.reply_to(message, "Processing your request, please wait...")
        if "instagram.com" in url and "/p/" not in url:
            # Profile URL detected
            try:
                downloaded_files = download_instagram_profile(url)
                for file_path in downloaded_files:
                    with open(file_path, 'rb') as media:
                        bot2.send_document(message.chat.id, media)
                    os.remove(file_path)
                bot2.reply_to(message, "All posts from the Instagram profile have been downloaded and sent.")
            except Exception as e:
                bot2.reply_to(message, f"Failed to download profile: {str(e)}")
        else:
            # Single post or other URLs
            try:
                file_path = download_media(url)
                with open(file_path, 'rb') as media:
                    bot2.send_document(message.chat.id, media)
                os.remove(file_path)
            except Exception as e:
                bot2.reply_to(message, f"Download failed: {str(e)}")
    else:
        bot2.reply_to(message, "Invalid or unsupported URL.")

@app.route('/' + API_TOKEN_2, methods=['POST'])
def bot_webhook():
    bot2.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "OK", 200

@app.route('/')
def set_webhook():
    bot2.remove_webhook()
    bot2.set_webhook(url=f"{KOYEB_URL}/{API_TOKEN_2}")
    return "Webhook set", 200

# Run Flask app
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080, debug=True)