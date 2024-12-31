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

# Download media using yt-dlp
def download_media(url, start_time=None, end_time=None):
    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'outtmpl': f'{output_dir}{sanitize_filename("%(title)s")}.%(ext)s',
        'cookiefile': cookies_file,
        'postprocessors': [{'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'}],
        'socket_timeout': 10,
        'retries': 5,
    }

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

# Upload file to a specific folder on Mega.nz
def upload_to_mega(file_path, folder_name=None):
    if mega_client is None:
        raise Exception("Mega client is not logged in. Use /meganz <username> <password> to log in.")

    try:
        folder = None
        if folder_name:
            folder = [f for f in mega_client.get_files().values() if f['a'].get('n') == folder_name]
            if not folder:
                raise Exception(f"Folder '{folder_name}' not found on Mega.nz")
            folder = folder[0]

        if folder:
            file = mega_client.upload(file_path, folder[0])
        else:
            file = mega_client.upload(file_path)

        public_link = mega_client.get_upload_link(file)
        return public_link
    except Exception as e:
        logging.error("Error uploading to Mega", exc_info=True)
        raise

# Handle download and upload logic
def handle_download_and_upload(message, url, upload_to_mega_flag, folder_name=None):
    if not is_valid_url(url):
        bot2.reply_to(message, "Invalid or unsupported URL. Supported platforms: YouTube, Instagram, Twitter, Facebook.")
        return

    try:
        bot2.reply_to(message, "Downloading the video, please wait...")

        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        start_time = query_params.get('start', [None])[0]
        end_time = query_params.get('end', [None])[0]

        file_path = download_media(url, start_time, end_time)

        if upload_to_mega_flag:
            bot2.reply_to(message, f"Uploading the video to Mega.nz folder '{folder_name}' if specified, please wait...")
            mega_link = upload_to_mega(file_path, folder_name)
            bot2.reply_to(message, f"Video has been uploaded to Mega.nz: {mega_link}")
        else:
            with open(file_path, 'rb') as video:
                bot2.send_video(message.chat.id, video)

        os.remove(file_path)
    except Exception as e:
        logging.error("Download or upload failed", exc_info=True)
        bot2.reply_to(message, f"Download or upload failed: {str(e)}")

# Mega login command
@bot2.message_handler(commands=['meganz'])
def handle_mega_login(message):
    global mega_client
    try:
        args = message.text.split(maxsplit=2)
        if len(args) == 1:
            mega_client = Mega().login()
            bot2.reply_to(message, "Logged in to Mega.nz anonymously!")
        elif len(args) == 3:
            email, password = args[1], args[2]
            retries = 3
            for attempt in range(retries):
                try:
                    mega_client = Mega().login(email, password)
                    bot2.reply_to(message, "Successfully logged in to Mega.nz!")
                    break
                except Exception as e:
                    bot2.reply_to(message, f"Login attempt {attempt + 1} failed: {str(e)}")
                    if attempt < retries - 1:
                        time.sleep(5)
        else:
            bot2.reply_to(message, "Usage: /meganz <username> <password> or /meganz for anonymous login")
    except Exception as e:
        bot2.reply_to(message, f"Login failed: {str(e)}")

# Handle Mega download and upload
@bot2.message_handler(commands=['mega'])
def handle_mega(message):
    try:
        args = message.text.split(maxsplit=2)
        if len(args) < 2:
            bot2.reply_to(message, "Usage: /mega <URL> [folder_name]")
            return

        url = args[1]
        folder_name = args[2] if len(args) > 2 else None
        handle_download_and_upload(message, url, upload_to_mega_flag=True, folder_name=folder_name)
    except Exception as e:
        bot2.reply_to(message, f"Error: {str(e)}")

# Direct download
@bot2.message_handler(func=lambda message: True, content_types=['text'])
def handle_direct_download(message):
    url = message.text.strip()
    if is_valid_url(url):
        handle_download_and_upload(message, url, upload_to_mega_flag=False)
    else:
        bot2.reply_to(message, "Please provide a valid URL to download the video.")

# Flask app for webhook
app = Flask(__name__)

@app.route('/' + API_TOKEN_2, methods=['POST'])
def bot_webhook():
    bot2.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "!", 200

@app.route('/')
def set_webhook():
    try:
        bot2.remove_webhook()
        bot2.set_webhook(url=KOYEB_URL + '/' + API_TOKEN_2, timeout=60)
        logging.info(f"Webhook set to: {KOYEB_URL}/{API_TOKEN_2}")
        return "Webhook set", 200
    except Exception as e:
        logging.error(f"Error setting webhook: {str(e)}")
        return f"Error: {str(e)}", 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=True)