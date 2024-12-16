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
from mega import Mega  # Mega SDK library

# Load API tokens and channel IDs from environment variables
API_TOKEN_2 = os.getenv('API_TOKEN_2')
CHANNEL_ID = os.getenv('CHANNEL_ID')  # Your Channel ID like '@YourChannel'

# Initialize the bot
bot2 = telebot.TeleBot(API_TOKEN_2, parse_mode='HTML')

# Directory to save downloaded files
output_dir = 'downloads/'
cookies_file = 'cookies.txt'

# Ensure the downloads directory exists
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# Logging configuration
logging.basicConfig(level=logging.DEBUG)

# Ensure yt-dlp is updated
def update_yt_dlp():
    try:
        result = subprocess.run(['yt-dlp', '-U'], capture_output=True, text=True, check=True)
        logging.info(f"yt-dlp updated: {result.stdout}")
    except subprocess.CalledProcessError as e:
        logging.error(f"yt-dlp update failed: {e.stderr}")
    except FileNotFoundError:
        logging.error("yt-dlp not found. Please install it before using this bot.")

update_yt_dlp()

# Supported domains
SUPPORTED_DOMAINS = ['youtube.com', 'youtu.be', 'instagram.com', 'x.com', 'facebook.com']

# Sanitize filename
def sanitize_filename(filename, max_length=250):
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)  # Remove invalid characters
    return filename.strip()[:max_length]

# Validate URL
def is_valid_url(url):
    try:
        result = urlparse(url)
        return result.scheme in ['http', 'https'] and any(domain in result.netloc for domain in SUPPORTED_DOMAINS)
    except ValueError:
        return False

# Parse time parameters
def parse_time_parameters(message_text):
    try:
        parts = message_text.split()
        url = parts[0]
        start_time, end_time = None, None
        if len(parts) > 1:
            matches = re.findall(r'(\d{1,2}:\d{2}:\d{2})', message_text)
            if len(matches) >= 1:
                start_time = matches[0]
            if len(matches) == 2:
                end_time = matches[1]
        return url, start_time, end_time
    except Exception as e:
        logging.error("Error parsing time parameters", exc_info=True)
        return None, None, None

# Download media
def download_media(url, start_time=None, end_time=None):
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
        if start_time or end_time:
            trimmed_file_path = file_path.replace(".mp4", "_trimmed.mp4")
            ffmpeg_cmd = f"ffmpeg -i \"{file_path}\" -ss {start_time or 0} -to {end_time or info_dict['duration']} -c copy \"{trimmed_file_path}\""
            os.system(ffmpeg_cmd)
            os.remove(file_path)
            file_path = trimmed_file_path
        return file_path
    except Exception as e:
        logging.error("yt-dlp download error", exc_info=True)
        raise

# Download and send media
def download_and_send(message, url, start_time=None, end_time=None):
    if not is_valid_url(url):
        bot2.reply_to(message, "Invalid or unsupported URL. Supported platforms: YouTube, Instagram, Twitter, Facebook.")
        return
    try:
        bot2.reply_to(message, "Downloading media, please wait...")
        with ThreadPoolExecutor(max_workers=3) as executor:
            file_path = executor.submit(download_media, url, start_time, end_time).result()
        with open(file_path, 'rb') as media:
            if file_path.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                bot2.send_photo(message.chat.id, media)
            elif file_path.lower().endswith('.mp4'):
                bot2.send_video(message.chat.id, media)
            else:
                bot2.send_document(message.chat.id, media)
        os.remove(file_path)
        bot2.reply_to(message, "Download and upload completed.")
    except Exception as e:
        logging.error("Download failed", exc_info=True)
        bot2.reply_to(message, f"Download failed: {str(e)}")

# Mega.nz login and download
mega_client = Mega()
mega_session = None

def mega_login_handler(message):
    try:
        credentials = message.text.split(maxsplit=1)[1]
        email, password = credentials.split()
        global mega_session
        mega_session = mega_client.login(email, password)
        bot2.reply_to(message, "Mega.nz login successful.")
    except Exception as e:
        logging.error("Mega.nz login failed", exc_info=True)
        bot2.reply_to(message, "Failed to log in to Mega.nz. Use `/meganz email password`.")

def mega_download_handler(message):
    if not mega_session:
        bot2.reply_to(message, "Log in to Mega.nz first using `/meganz email password`.")
        return
    try:
        link = message.text.split(maxsplit=1)[1]
        file = mega_session.download_url(link, dest_path=output_dir)
        bot2.reply_to(message, f"Download complete: {file}")
        with open(file, 'rb') as f:
            bot2.send_document(message.chat.id, f)
        os.remove(file)
    except Exception as e:
        logging.error("Mega.nz download failed", exc_info=True)
        bot2.reply_to(message, f"Mega.nz download failed: {str(e)}")

# Telegram command handlers
@bot2.message_handler(commands=['meganz'])
def handle_mega_login(message):
    mega_login_handler(message)

@bot2.message_handler(commands=['mega'])
def handle_mega_download(message):
    mega_download_handler(message)

@bot2.message_handler(func=lambda message: True)
def handle_links(message):
    url, start_time, end_time = parse_time_parameters(message.text)
    if url:
        threading.Thread(target=download_and_send, args=(message, url, start_time, end_time)).start()
    else:
        bot2.reply_to(message, "Invalid input. Provide a valid URL and optional time parameters.")

# Flask app setup
app = Flask(__name__)

@app.route('/' + API_TOKEN_2, methods=['POST'])
def bot_webhook():
    bot2.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "!", 200

@app.route('/')
def set_webhook():
    bot2.remove_webhook()
    bot2.set_webhook(url=os.getenv('KOYEB_URL') + '/' + API_TOKEN_2, timeout=60)
    return "Webhook set", 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080, debug=True)