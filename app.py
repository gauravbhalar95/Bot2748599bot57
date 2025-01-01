import os
import logging
from flask import Flask, request
import telebot
import yt_dlp
import re
from urllib.parse import urlparse
from mega import Mega
from datetime import datetime

# Environment variables
API_TOKEN_2 = os.getenv('API_TOKEN_2')
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

# Sanitize filenames
def sanitize_filename(filename, max_length=250):
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)
    return filename.strip()[:max_length]

# Add timestamp to filenames
def add_timestamp_to_filename(filename):
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    name, ext = os.path.splitext(filename)
    return f"{name}_{timestamp}{ext}"

# Validate URL
def is_valid_url(url):
    try:
        result = urlparse(url)
        return result.scheme in ['http', 'https'] and any(domain in result.netloc for domain in SUPPORTED_DOMAINS)
    except ValueError:
        return False

# Download media
def download_media(url, start_time=None, end_time=None):
    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'outtmpl': f'{output_dir}{sanitize_filename("%(title)s")}.%(ext)s',
        'cookiefile': cookies_file,
        'retries': 5,
    }
    if start_time or end_time:
        ydl_opts['postprocessor_args'] = []
        if start_time:
            ydl_opts['postprocessor_args'] += ['-ss', start_time]
        if end_time:
            ydl_opts['postprocessor_args'] += ['-to', end_time]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info_dict)
            timestamped_file_path = add_timestamp_to_filename(file_path)
            os.rename(file_path, timestamped_file_path)
        return timestamped_file_path
    except Exception as e:
        logging.error("yt-dlp download error", exc_info=True)
        raise

# Upload to Mega.nz
def upload_to_mega(file_path, folder_name=None):
    if not mega_client:
        raise Exception("Mega client is not logged in. Use /meganz <username> <password> to log in.")

    try:
        folder = None
        if folder_name:
            folders = mega_client.find(folder_name)
            if not folders:
                raise Exception(f"Folder '{folder_name}' not found on Mega.nz")
            folder = folders[0]

        file = mega_client.upload(file_path, folder) if folder else mega_client.upload(file_path)
        public_link = mega_client.get_upload_link(file)
        return public_link
    except Exception as e:
        logging.error("Mega upload error", exc_info=True)
        raise

# Handle download/upload
def handle_download_and_upload(message, url, upload_to_mega_flag, folder_name=None, start_time=None, end_time=None):
    if not is_valid_url(url):
        bot2.reply_to(message, "Invalid or unsupported URL. Supported platforms: YouTube, Instagram, Twitter, Facebook.")
        return

    try:
        bot2.reply_to(message, "Downloading the video, please wait...")
        file_path = download_media(url, start_time, end_time)

        if upload_to_mega_flag:
            bot2.reply_to(message, f"Uploading to Mega.nz folder '{folder_name}', please wait...")
            mega_link = upload_to_mega(file_path, folder_name)
            bot2.reply_to(message, f"Uploaded to Mega.nz: {mega_link}")
        else:
            with open(file_path, 'rb') as video:
                bot2.send_video(message.chat.id, video)

        os.remove(file_path)
    except Exception as e:
        logging.error("Download or upload failed", exc_info=True)
        bot2.reply_to(message, f"Failed: {str(e)}")

# Mega login
@bot2.message_handler(commands=['meganz'])
def handle_mega_login(message):
    global mega_client
    try:
        args = message.text.split(maxsplit=2)
        if len(args) == 1:
            mega_client = Mega().login()  # Anonymous login
            bot2.reply_to(message, "Logged in to Mega.nz anonymously!")
        elif len(args) == 3:
            email, password = args[1], args[2]
            mega_client = Mega().login(email, password)
            bot2.reply_to(message, "Successfully logged in to Mega.nz!")
        else:
            bot2.reply_to(message, "Usage: /meganz <username> <password> or /meganz for anonymous login")
    except Exception as e:
        bot2.reply_to(message, f"Login failed: {str(e)}")

# Handle /mega command
@bot2.message_handler(commands=['mega'])
def handle_mega(message):
    args = message.text.split(maxsplit=2)
    if len(args) < 2:
        bot2.reply_to(message, "Usage: /mega <URL> [folder_name]")
        return

    url = args[1]
    folder_name = args[2] if len(args) > 2 else None
    handle_download_and_upload(message, url, upload_to_mega_flag=True, folder_name=folder_name)

# Direct download
@bot2.message_handler(func=lambda message: True, content_types=['text'])
def handle_direct_download(message):
    url = message.text.strip()
    if is_valid_url(url):
        handle_download_and_upload(message, url, upload_to_mega_flag=False)
    else:
        bot2.reply_to(message, "Please provide a valid URL to download the video.")

# Flask app
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