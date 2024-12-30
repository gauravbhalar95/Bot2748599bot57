import os
import logging
from flask import Flask, request
import telebot
import yt_dlp
import re
from urllib.parse import urlparse
from mega import Mega  # Mega.nz Python library
from decoder import decode_file, validate_data  # Import functions from decoder.py

# Load environment variables
API_TOKEN_2 = os.getenv('API_TOKEN_2')
CHANNEL_ID = os.getenv('CHANNEL_ID')  # Example: '@YourChannel'
KOYEB_URL = os.getenv('KOYEB_URL')  # Koyeb URL for webhook

# Initialize bot
bot2 = telebot.TeleBot(API_TOKEN_2, parse_mode='HTML')

# Directories for downloads and processed files
output_dir = 'downloads/'
processed_dir = 'processed/'
cookies_file = 'cookies.txt'

# Ensure directories exist
for directory in [output_dir, processed_dir]:
    if not os.path.exists(directory):
        os.makedirs(directory)

# Logging configuration
logging.basicConfig(level=logging.DEBUG)

# Supported domains for URL validation
SUPPORTED_DOMAINS = ['youtube.com', 'youtu.be', 'instagram.com', 'x.com', 'facebook.com']

# Mega client for file uploads
mega_client = None

# Sanitize filenames for downloaded files
def sanitize_filename(filename, max_length=250):
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)
    return filename.strip()[:max_length]

# Check if the URL is valid and belongs to supported domains
def is_valid_url(url):
    try:
        result = urlparse(url)
        return result.scheme in ['http', 'https'] and any(domain in result.netloc for domain in SUPPORTED_DOMAINS)
    except ValueError:
        return False

# Download media using yt-dlp
def download_media(url, start_time=None, end_time=None):
    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'outtmpl': f'{output_dir}{sanitize_filename("%(title)s")}.%(ext)s',
        'cookiefile': cookies_file,
    }

    # Set the start and end time for trimming the video
    if start_time and end_time:
        ydl_opts['postprocessor_args'] = ['-ss', start_time, '-to', end_time]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info_dict)
        return file_path
    except Exception as e:
        logging.error("yt-dlp download error", exc_info=True)
        raise

# Upload file to Mega.nz
def upload_to_mega(file_path):
    if mega_client is None:
        raise Exception("Mega client is not logged in. Use /meganz <username> <password> to log in.")

    try:
        file = mega_client.upload(file_path)
        public_link = mega_client.get_upload_link(file)
        return public_link
    except Exception as e:
        logging.error("Error uploading to Mega", exc_info=True)
        raise

# Handle download and upload logic
def handle_download_and_upload(message, url, upload_to_mega_flag):
    if not is_valid_url(url):
        bot2.reply_to(message, "Invalid or unsupported URL.")
        return

    try:
        bot2.reply_to(message, "Downloading the video, please wait...")
        file_path = download_media(url)

        # Decode the file
        decoded_file = decode_file(file_path)

        if not validate_data(decoded_file):
            bot2.reply_to(message, "Failed to process the downloaded file.")
            return

        # Upload to Mega or send the video to Telegram
        if upload_to_mega_flag:
            bot2.reply_to(message, "Uploading to Mega.nz...")
            mega_link = upload_to_mega(decoded_file)
            bot2.reply_to(message, f"Uploaded to Mega.nz: {mega_link}")
        else:
            with open(decoded_file, 'rb') as video:
                bot2.send_video(message.chat.id, video)

        # Cleanup
        os.remove(file_path)
    except Exception as e:
        logging.error("Error during handling", exc_info=True)
        bot2.reply_to(message, f"An error occurred: {str(e)}")

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