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

# Function to check the user status in the channel
def check_user_status(user_id):
    try:
        member = bot2.get_chat_member(CHANNEL_ID, user_id)
        logging.info(f"User status: {member.status}")
        if member.status in ['administrator', 'creator']:
            return 'admin'
        elif member.status == 'member':
            return 'member'
        elif member.status == 'kicked':
            return 'banned'
        else:
            return 'not_member'
    except Exception as e:
        logging.error(f"Error checking user status: {e}")
        return 'error'

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

    ydl_opts = {
        'format': 'best',
        'outtmpl': f'{output_dir}%(title)s.%(ext)s',
        'cookiefile': cookies_file if os.path.exists(cookies_file) else None,
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }],
        'socket_timeout': 60,
    }

    # Handle different platforms
    if 'instagram.com' in url:
        logging.info("Processing Instagram URL")
        if '/stories/' in url:
            ydl_opts['outtmpl'] = f'{output_dir}%(uploader)s_story.%(ext)s'
        elif any(path in url for path in ['/reel/', '/p/', '/tv/']):
            ydl_opts['outtmpl'] = f'{output_dir}%(title)s.%(ext)s'
    elif any(domain in url for domain in ['twitter.com', 'x.com', 'threads.com', 'youtube.com', 'youtu.be']):
        logging.info("Processing Twitter/X/Threads/YouTube URL")
    elif 'facebook.com' in url:
        logging.info("Processing Facebook URL")
    elif 'youtube.com' in url or 'youtu.be' in url:
        logging.info("Processing YouTube URL")
    else:
        logging.error(f"Unsupported URL: {url}")
        raise Exception("Unsupported URL!")

    # Download using yt-dlp
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info_dict)
        return file_path
    except Exception as e:
        logging.error(f"yt-dlp download error: {str(e)}")
        raise

# Function to download media and send it asynchronously with progress
def download_and_send(message, url):
    try:
        bot2.reply_to(message, "Downloading media, this may take some time...")

        with ThreadPoolExecutor(max_workers=10) as executor:
            future = executor.submit(download_media, url)
            file_path = future.result()

            file_size = os.path.getsize(file_path)
            if file_size > 50 * 1024 * 1024:
                bot2.reply_to(message, "The file is too large to be sent via Telegram.")
                os.remove(file_path)
                return

            with open(file_path, 'rb') as media:
                if file_path.lower().endswith('.mp4'):
                    bot2.send_video(message.chat.id, media)
                elif file_path.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                    bot2.send_photo(message.chat.id, media)
                else:
                    bot2.send_document(message.chat.id, media)

            os.remove(file_path)

    except Exception as e:
        bot2.reply_to(message, f"Failed to download. Error: {str(e)}")
        logging.error(f"Download failed: {e}")

# Function to run tasks after admin verification
def run_task(message):
    try:
        url = message.text
        user_id = message.from_user.id
        status = check_user_status(user_id)

        if status == 'admin':
            bot2.reply_to(message, "Admin verification successful. Starting download...")
            download_and_send(message, url)
        elif status == 'member':
            bot2.reply_to(message, "Hello Member! You cannot start this task. Please contact an admin.")
        elif status == 'banned':
            bot2.reply_to(message, "You are banned from the channel.")
        elif status == 'not_member':
            bot2.reply_to(message, f"Please join the channel first: {CHANNEL_ID}")
        else:
            bot2.reply_to(message, "There was an error checking your status. Please try again later.")
    except Exception as e:
        bot2.reply_to(message, f"Failed to run task. Error: {str(e)}")
        logging.error(f"Task execution failed: {e}")

# Flask app setup
app = Flask(__name__)
app.config['DEBUG'] = True

# Bot 2 commands and handlers
@bot2.message_handler(commands=['start'])
def send_welcome_bot2(message):
    bot2.reply_to(message, "Welcome! Paste the link of the content you want to download.")

# Handle media links
@bot2.message_handler(func=lambda message: True)
def handle_links(message):
    url = message.text
    threading.Thread(target=run_task, args=(message,)).start()

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
    return "Failed to set webhook after retries", 500

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
