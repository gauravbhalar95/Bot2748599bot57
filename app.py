import os
import logging
import threading
from flask import Flask, request
import telebot
import yt_dlp
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, parse_qs
import subprocess
import traceback
import re
import time
from mega import Mega

# Load API tokens and channel IDs from environment variables
API_TOKEN_2 = os.getenv('API_TOKEN_2')
CHANNEL_ID = os.getenv('CHANNEL_ID')

# Initialize the bot
bot2 = telebot.TeleBot(API_TOKEN_2, parse_mode='HTML')
telebot.logger.setLevel(logging.DEBUG)

# Directory to save downloaded files
output_dir = 'downloads/'
cookies_file = 'cookies.txt'

# Mega.nz login details
mega_username = None
mega_password = None

# Ensure the downloads directory exists
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

# Ensure yt-dlp is updated
def update_yt_dlp():
    try:
        subprocess.run(['yt-dlp', '-U'], check=True)
    except Exception as e:
        logging.error(f"Failed to update yt-dlp: {e}")

update_yt_dlp()

SUPPORTED_DOMAINS = ['youtube.com', 'youtu.be', 'instagram.com', 'x.com', 'facebook.com']

# Sanitize filename
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

# Function to handle Mega.nz login
def mega_login():
    global mega_username, mega_password
    if mega_username and mega_password:
        mega = Mega()
        try:
            m = mega.login(mega_username, mega_password)
            return m
        except Exception as e:
            logging.error(f"Mega.nz login failed: {e}")
    return None

# Upload to Mega.nz
def upload_to_mega(file_path):
    try:
        mega = mega_login()
        if not mega:
            return None
        uploaded_file = mega.upload(file_path)
        public_url = mega.get_upload_link(uploaded_file)
        return public_url
    except Exception as e:
        logging.error(f"Error uploading to Mega.nz: {e}")
        return None

# Download media
def download_media(url):
    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'outtmpl': f'{output_dir}{sanitize_filename("%(title)s")}.%(ext)s',
        'cookiefile': cookies_file,
        'quiet': False
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info_dict)
            return file_path
    except Exception as e:
        logging.error(f"Error downloading media: {e}")
        return None

# Download and send file
def download_and_send(message, url):
    if not is_valid_url(url):
        bot2.reply_to(message, "Invalid URL or unsupported platform.")
        return

    bot2.reply_to(message, "Downloading... Please wait.")
    try:
        file_path = download_media(url)
        if file_path and os.path.exists(file_path):
            with open(file_path, 'rb') as media:
                if file_path.endswith(('.mp4', '.mov')):
                    bot2.send_video(message.chat.id, media)
                elif file_path.endswith(('.jpg', '.jpeg', '.png', '.gif')):
                    bot2.send_photo(message.chat.id, media)
                else:
                    bot2.send_document(message.chat.id, media)

            mega_url = upload_to_mega(file_path)
            if mega_url:
                bot2.reply_to(message, f"File uploaded to Mega.nz: {mega_url}")
            else:
                bot2.reply_to(message, "Failed to upload to Mega.nz.")
            os.remove(file_path)
        else:
            bot2.reply_to(message, "Failed to download the file.")
    except Exception as e:
        logging.error(f"Error: {e}")
        bot2.reply_to(message, f"An error occurred: {e}")

# Command to handle downloads
@bot2.message_handler(commands=['download'])
def handle_download(message):
    url = message.text.split(maxsplit=1)[-1]
    threading.Thread(target=download_and_send, args=(message, url)).start()

# Mega.nz credentials command
@bot2.message_handler(commands=['meganz'])
def set_mega_credentials(message):
    bot2.reply_to(message, "Send Mega.nz username and password in this format:\nusername password")
    bot2.register_next_step_handler(message, save_mega_credentials)

def save_mega_credentials(message):
    global mega_username, mega_password
    try:
        creds = message.text.split()
        if len(creds) == 2:
            mega_username, mega_password = creds
            bot2.reply_to(message, "Mega.nz credentials saved.")
        else:
            bot2.reply_to(message, "Invalid format. Use: username password")
    except Exception as e:
        logging.error(f"Error saving Mega credentials: {e}")
        bot2.reply_to(message, "Failed to save credentials.")

# Flask app
app = Flask(__name__)

@app.route('/' + API_TOKEN_2, methods=['POST'])
def webhook_handler():
    bot2.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "OK", 200

@app.route('/')
def webhook():
    bot2.remove_webhook()
    bot2.set_webhook(url=os.getenv('KOYEB_URL') + '/' + API_TOKEN_2)
    return "Webhook set", 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080, debug=True)