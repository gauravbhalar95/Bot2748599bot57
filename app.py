import os
import logging
import re
import threading
from flask import Flask, request
import telebot
import yt_dlp
from urllib.parse import urlparse
from mega import Mega
from concurrent.futures import ThreadPoolExecutor

# Load environment variables
API_TOKEN_2 = os.getenv('API_TOKEN_2')
KOYEB_URL = os.getenv('KOYEB_URL')
CHANNEL_ID = os.getenv('CHANNEL_ID')  # For broadcasting to a specific channel

# Initialize bot
bot2 = telebot.TeleBot(API_TOKEN_2, parse_mode='HTML')

# Directories and cookies
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

# yt-dlp downloader function
def download_media(url, platform=None):
    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'outtmpl': f'{output_dir}{sanitize_filename("%(title)s")}.%(ext)s',
        'cookiefile': cookies_file,
        'postprocessors': [{'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'}],
        'socket_timeout': 10,
        'retries': 5,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info_dict)
        return file_path
    except Exception as e:
        logging.error(f"yt-dlp download error for {platform}: {e}", exc_info=True)
        raise

# Upload file to Mega.nz
def upload_to_mega(file_path, folder_name=None):
    if mega_client is None:
        raise Exception("Mega client is not logged in. Use /meganz <username> <password> to log in.")
    try:
        if folder_name:
            folder = mega_client.find(folder_name)
            if not folder:
                folder = mega_client.create_folder(folder_name)
            file = mega_client.upload(file_path, folder[0])
        else:
            file = mega_client.upload(file_path)
        public_link = mega_client.get_upload_link(file)
        return public_link
    except Exception as e:
        logging.error("Error uploading to Mega", exc_info=True)
        raise

# Login to Mega.nz
@bot2.message_handler(commands=['meganz'])
def handle_mega_login(message):
    global mega_client
    try:
        args = message.text.split(maxsplit=2)
        if len(args) == 1:
            mega_client = Mega().login()  # Anonymous login
            bot2.reply_to(message, "Logged in to Mega.nz anonymously!")
        elif len(args) == 3:
            email = args[1]
            password = args[2]
            mega_client = Mega().login(email, password)
            bot2.reply_to(message, "Successfully logged in to Mega.nz!")
        else:
            bot2.reply_to(message, "Usage: /meganz <username> <password> or /meganz for anonymous login")
    except Exception as e:
        bot2.reply_to(message, f"Login failed: {str(e)}")

# General download and send
def download_and_send(message, url, platform=None):
    if not is_valid_url(url):
        bot2.reply_to(message, "Invalid URL. Supported platforms: YouTube, Instagram, Twitter, Facebook.")
        return

    try:
        bot2.reply_to(message, f"Downloading {platform} media, please wait...")
        file_path = download_media(url, platform)

        # Send media
        with open(file_path, 'rb') as media:
            if file_path.lower().endswith('.mp4'):
                bot2.send_video(message.chat.id, media)
            else:
                bot2.send_document(message.chat.id, media)

        # Cleanup
        os.remove(file_path)
    except Exception as e:
        bot2.reply_to(message, f"Failed to download {platform} media. Error: {str(e)}")
        logging.error(f"Error downloading {platform} media: {e}")

# Platform-specific handlers
@bot2.message_handler(commands=['instagram'])
def handle_instagram(message):
    url = message.text.split(maxsplit=1)[-1]
    threading.Thread(target=download_and_send, args=(message, url, "Instagram")).start()

@bot2.message_handler(commands=['twitter'])
def handle_twitter(message):
    url = message.text.split(maxsplit=1)[-1]
    threading.Thread(target=download_and_send, args=(message, url, "Twitter")).start()

@bot2.message_handler(commands=['facebook'])
def handle_facebook(message):
    url = message.text.split(maxsplit=1)[-1]
    threading.Thread(target=download_and_send, args=(message, url, "Facebook")).start()

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