import os
import logging
import threading
from flask import Flask, request
import telebot
import yt_dlp
import requests
from concurrent.futures import ThreadPoolExecutor
import time

# Load API tokens and channel IDs from environment variables
API_TOKEN_2 = os.getenv('API_TOKEN_2')  # Your bot token
CHANNEL_ID = os.getenv('CHANNEL_ID')  # Your Telegram channel ID, like '@YourChannel'
KOYEB_URL = os.getenv("KOYEB_URL")  # Koyeb deployment URL

# Initialize the bot
bot2 = telebot.TeleBot(API_TOKEN_2)

# Directory to save downloaded files
output_dir = 'downloads/'
cookies_file = 'cookies.txt'

# Create the downloads directory if it does not exist
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# Logging setup
logging.basicConfig(level=logging.DEBUG)

# Function to sanitize filenames
def sanitize_filename(filename, max_length=200):
    import re
    filename = re.sub(r'[\\/*?:"<>|]', "_", filename)
    filename = re.sub(r'https?://\S+', '', filename)  # Remove URLs from the filename
    filename = filename.strip()[:max_length]
    return filename

# Function to download media
def download_media(url):
    logging.info(f"Attempting to download media from URL: {url}")

    if 'instagram.com' in url:
        logging.info("Processing Instagram URL")
        ydl_opts = {
            'format': 'best',
            'outtmpl': f'{output_dir}%(title)s.%(ext)s',
            'cookiefile': cookies_file,
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
            'socket_timeout': 15,
        }
        if '/stories/' in url:
            ydl_opts['format'] = 'bestvideo+bestaudio/best'
            ydl_opts['outtmpl'] = f'{output_dir}%(uploader)s_story.%(ext)s'
        elif '/reel/' in url or '/p/' in url or '/tv/' in url:
            ydl_opts['format'] = 'best'
            ydl_opts['outtmpl'] = f'{output_dir}%(title)s.%(ext)s'

    elif 'twitter.com' in url or 'x.com' in url or 'threads.com' in url:
        logging.info("Processing Twitter/Threads/X URL")
        ydl_opts = {
            'format': 'best',
            'outtmpl': f'{output_dir}%(title)s.%(ext)s',
            'cookiefile': cookies_file,
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
            'socket_timeout': 15,
        }

    elif 'youtube.com' in url or 'youtu.be' in url:
        logging.info("Processing YouTube URL")
        ydl_opts = {
            'format': 'best',
            'outtmpl': f'{output_dir}%(title)s.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
            'socket_timeout': 15,
            'cookiefile': cookies_file,
        }

    elif 'facebook.com' in url:
        logging.info("Processing Facebook URL")
        ydl_opts = {
            'format': 'best',
            'outtmpl': f'{output_dir}%(title)s.%(ext)s',
            'socket_timeout': 15,
        }

    else:
        logging.error(f"Unsupported URL: {url}")
        raise Exception("Unsupported URL!")

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info_dict)
        return file_path
    except Exception as e:
        logging.error(f"yt-dlp download error: {str(e)}")
        raise

# Function to download all media from a URL
def download_all_media(url):
    logging.info(f"Attempting to download all media from URL: {url}")

    ydl_opts = {
        'format': 'best',
        'outtmpl': f'{output_dir}%(title)s.%(ext)s',
        'cookiefile': cookies_file,
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }],
        'socket_timeout': 15,
    }

    if 'instagram.com' in url:
        logging.info("Processing Instagram URL for all media")
        ydl_opts['extract_flat'] = True  # Extract video URLs without downloading
        ydl_opts['noplaylist'] = True  # Prevent playlist download

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            return [ydl.prepare_filename(entry) for entry in info_dict['entries']]
    except Exception as e:
        logging.error(f"yt-dlp download error: {str(e)}")
        raise

# Function to download media and send it asynchronously
def download_and_send(message, url):
    try:
        bot2.reply_to(message, "Downloading media, this may take some time...")

        with ThreadPoolExecutor(max_workers=5) as executor:  # Adjusted for performance
            future = executor.submit(download_media, url)
            file_path = future.result()

            with open(file_path, 'rb') as media:
                if file_path.lower().endswith(('.mp4', '.mkv', '.webm')):
                    bot2.send_video(message.chat.id, media)
                elif file_path.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                    bot2.send_photo(message.chat.id, media)
                else:
                    bot2.send_document(message.chat.id, media)

            os.remove(file_path)

    except Exception as e:
        bot2.reply_to(message, f"Failed to download. Error: {str(e)}")
        logging.error(f"Download failed: {e}")

# Function to download all media and send it asynchronously
def download_and_send_all(message, url):
    try:
        bot2.reply_to(message, "Downloading all media, this may take some time...")
        media_files = download_all_media(url)

        for file_path in media_files:
            with open(file_path, 'rb') as media:
                if file_path.lower().endswith(('.mp4', '.mkv', '.webm')):
                    bot2.send_video(message.chat.id, media)
                elif file_path.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                    bot2.send_photo(message.chat.id, media)
                else:
                    bot2.send_document(message.chat.id, media)

            os.remove(file_path)

    except Exception as e:
        bot2.reply_to(message, f"Failed to download all media. Error: {str(e)}")
        logging.error(f"Download all media failed: {e}")

# Function to handle links and download media automatically
def handle_links(message):
    url = message.text
    if any(keyword in url for keyword in ['instagram.com', 'twitter.com', 'youtube.com', 'facebook.com']):
        download_and_send_all(message, url)  # Download all media automatically
    else:
        bot2.reply_to(message, "Unsupported URL. Please send a valid media link.")

# Flask app setup
app = Flask(__name__)
app.config['DEBUG'] = True

# Bot 2 commands and handlers
@bot2.message_handler(commands=['start'])
def send_welcome_bot2(message):
    bot2.reply_to(message, "Welcome! To download media from Instagram, Twitter, Facebook, or YouTube, please send the link you want to download.")

# Handle media links automatically
@bot2.message_handler(func=lambda message: True)
def handle_message(message):
    handle_links(message)

# Flask routes for webhook handling
@app.route('/' + API_TOKEN_2, methods=['POST'])
def getMessage_bot2():
    bot2.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "!", 200

@app.route('/')
def webhook():
    bot2.remove_webhook()
    retries = 3
    while retries > 0:
        try:
            webhook_url = f'https://{KOYEB_URL}/{API_TOKEN_2}'
            bot2.set_webhook(url=webhook_url, timeout=60)
            logging.info(f"Webhook set to {webhook_url}")
            return "Webhook set", 200
        except requests.exceptions.ConnectionError as e:
            logging.error(f"Connection error: {e}")
            retries -= 1
            time.sleep(5)
    return "Webhook failed to set", 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
