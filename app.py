import os
import logging
import threading
import time
from flask import Flask, request
import telebot
import yt_dlp
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
from datetime import datetime, timedelta
from PIL import Image
import shutil

# Load API tokens and channel IDs from environment variables
API_TOKEN_2 = os.getenv('API_TOKEN_2')
CHANNEL_ID = os.getenv('CHANNEL_ID')  # Your Channel ID with @ like '@YourChannel'

# Initialize the bot
bot2 = telebot.TeleBot(API_TOKEN_2, parse_mode='HTML')
telebot.logger.setLevel(logging.DEBUG)

# Directory to save downloaded files
output_dir = 'downloads/'
cookies_file = 'cookies.txt'  # YouTube cookies file

# Ensure the downloads directory exists
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

# Ensure yt-dlp is updated
os.system('yt-dlp -U')

# Rate limiting and access control
user_download_limits = {}  # Track download requests per user
RATE_LIMIT = 5  # Maximum downloads allowed per user per hour

# Function to sanitize filenames
def sanitize_filename(filename, max_length=250):
    import re
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)  # Remove invalid characters
    return filename.strip()[:max_length]

# Function to validate URLs
def is_valid_url(url):
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

# Function to preview metadata
def preview_metadata(url):
    try:
        with yt_dlp.YoutubeDL() as ydl:
            info_dict = ydl.extract_info(url, download=False)
            title = info_dict.get('title', 'N/A')
            duration = info_dict.get('duration', 'N/A')
            return f"Title: {title}\nDuration: {duration}s"
    except Exception as e:
        logging.error(f"Metadata preview error: {str(e)}")
        return "Unable to retrieve metadata."

# Function to download media
def download_media(url, custom_name=None, username=None, password=None, use_proxy=None):
    logging.debug(f"Attempting to download media from URL: {url}")

    # Set up output template with optional custom name
    if custom_name:
        output_template = f'{output_dir}{sanitize_filename(custom_name)}.%(ext)s'
    else:
        output_template = f'{output_dir}{sanitize_filename("%(title)s")}.%(ext)s'

    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'outtmpl': output_template,
        'cookiefile': cookies_file,
        'postprocessors': [{'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'}],
        'socket_timeout': 10,
        'retries': 5,
        'progress_hooks': [download_progress_hook],
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.85 Safari/537.36'
    }

    if username and password:
        ydl_opts['username'] = username
        ydl_opts['password'] = password

    if use_proxy:
        ydl_opts['proxy'] = use_proxy

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info_dict)

        if not os.path.exists(file_path):
            part_file_path = f"{file_path}.part"
            if os.path.exists(part_file_path):
                os.rename(part_file_path, file_path)
                logging.debug(f"Renamed partial file: {part_file_path} to {file_path}")
            else:
                logging.error(f"Downloaded file not found at path: {file_path}")
                raise Exception("Download failed: File not found after download.")

        create_thumbnail(file_path)
        return file_path

    except Exception as e:
        logging.error(f"yt-dlp download error: {str(e)}")
        raise

# Download progress hook function
def download_progress_hook(d):
    if d['status'] == 'downloading':
        percent = d.get('_percent_str', '0%')
        eta = d.get('eta', 0)
        print(f"Download progress: {percent} - ETA: {eta}s")

# Function to create video thumbnails
def create_thumbnail(video_path):
    try:
        from moviepy.editor import VideoFileClip
        clip = VideoFileClip(video_path)
        thumbnail_path = f"{video_path}.jpg"
        clip.save_frame(thumbnail_path, t=1.0)
        clip.close()
        logging.debug(f"Thumbnail saved at: {thumbnail_path}")
    except Exception as e:
        logging.error(f"Thumbnail creation failed: {str(e)}")

# Schedule downloads
def schedule_download(message, url, custom_name=None, username=None, password=None, delay=60):
    time.sleep(delay)
    download_and_send(message, url, custom_name, username, password)

# Function to handle downloading and sending files asynchronously
def download_and_send(message, url, custom_name=None, username=None, password=None, use_proxy=None):
    if not is_valid_url(url):
        bot2.reply_to(message, "The provided URL is not valid. Please enter a valid URL.")
        return

    if user_download_limits.get(message.chat.id, 0) >= RATE_LIMIT:
        bot2.reply_to(message, "You have reached the download limit. Please try again later.")
        return

    try:
        metadata = preview_metadata(url)
        bot2.reply_to(message, f"Downloading media. Preview:\n{metadata}")

        logging.debug("Initiating media download")
        with ThreadPoolExecutor(max_workers=3) as executor:
            future = executor.submit(download_media, url, custom_name, username, password, use_proxy)
            file_path = future.result()

            logging.debug(f"Download completed, file path: {file_path}")

            if file_path.lower().endswith('.mp4'):
                with open(file_path, 'rb') as media:
                    bot2.send_video(message.chat.id, media)
            else:
                with open(file_path, 'rb') as media:
                    if file_path.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                        bot2.send_photo(message.chat.id, media)
                    else:
                        bot2.send_document(message.chat.id, media)

            os.remove(file_path)
            bot2.reply_to(message, "Download and sending completed successfully.")
            user_download_limits[message.chat.id] = user_download_limits.get(message.chat.id, 0) + 1

    except Exception as e:
        bot2.reply_to(message, f"Failed to download. Error: {str(e)}")
        logging.error(f"Download failed: {e}")

# Remove old files
def cleanup_old_files(days=1):
    now = time.time()
    for filename in os.listdir(output_dir):
        file_path = os.path.join(output_dir, filename)
        if os.path.isfile(file_path) and os.stat(file_path).st_mtime < now - days * 86400:
            os.remove(file_path)
            logging.debug(f"Deleted old file: {file_path}")

# Function to handle messages
@bot2.message_handler(func=lambda message: True)
def handle_links(message):
    text = message.text.split(' ', 1)  # Split input into URL and optional custom name
    url = text[0]
    custom_name = text[1].strip() if len(text) > 1 else None

    username = None
    password = None
    if "@" in url:
        username, password = url.split('@', 1)
        url = password

    # Schedule downloads if needed
    threading.Thread(target=schedule_download, args=(message, url, custom_name, username, password)).start()

# Flask app setup
app = Flask(__name__)

# Flask routes for webhook handling
@app.route('/' + API_TOKEN_2, methods=['POST'])
def getMessage_bot2():
    bot2.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "!", 200

@app.route('/')
def webhook():
    bot2.remove_webhook()
    bot2.set_webhook(url=os.getenv('KOYEB_URL') + '/' + API_TOKEN_2, timeout=60)
    return "Webhook set", 200

if __name__ == "__main__":
    threading.Thread(target=cleanup_old_files).start()
    app.run(host='0.0.0.0', port=8080, debug=True)