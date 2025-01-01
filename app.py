import os
import logging
import re
from flask import Flask, request
import telebot
import yt_dlp
from urllib.parse import urlparse
from mega import Mega

# Load environment variables
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
SUPPORTED_DOMAINS = ['youtube.com', 'youtu.be', 'instagram.com', 'x.com', 'facebook.com', 'pinterest.com']

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

# Parse YouTube URL with optional start and end times
def parse_youtube_url(url):
    match = re.match(r'(https?://[^\s]+)\s+(\d+)-(\d+)', url)
    if match:
        url, start, end = match.groups()
        return url, int(start), int(end)
    return url, None, None

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

    # Add trimming options if start_time and end_time are provided
    if start_time is not None and end_time is not None:
        ydl_opts['postprocessors'].append({
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
            'postprocessor_args': ['-ss', str(start_time), '-to', str(end_time)],
        })

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info_dict)
        return file_path
    except Exception as e:
        logging.error("yt-dlp download error", exc_info=True)
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

# Mega login command
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

# Mega command with folder support
@bot2.message_handler(commands=['mega'])
def handle_mega(message):
    global mega_client
    try:
        args = message.text.split(maxsplit=2)
        if len(args) < 2:
            bot2.reply_to(message, "Usage: /mega <URL> [folder]\nExample: /mega https://example.com/video.mp4 MyFolder")
            return

        url = args[1]
        folder_name = args[2] if len(args) > 2 else None  # Optional folder name

        if not is_valid_url(url):
            bot2.reply_to(message, "Invalid or unsupported URL. Supported platforms: YouTube, Instagram, Twitter, Facebook, Pinterest.")
            return

        url, start_time, end_time = parse_youtube_url(url)

        bot2.reply_to(message, "Downloading the video, please wait...")

        # Download media
        file_path = download_media(url, start_time, end_time)

        # Upload to Mega.nz
        bot2.reply_to(message, "Uploading the video to Mega.nz, please wait...")
        mega_link = upload_to_mega(file_path, folder_name)
        bot2.reply_to(message, f"Video has been uploaded to Mega.nz: {mega_link}")

        # Cleanup
        os.remove(file_path)

    except Exception as e:
        logging.error("Error in /mega command", exc_info=True)
        bot2.reply_to(message, f"Failed to handle the /mega command: {str(e)}")

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