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
API_TOKEN = os.getenv('API_TOKEN')  # Your bot token
CHANNEL_ID = os.getenv('CHANNEL_ID')  # Your Telegram channel ID, like '@YourChannel'
KOYEB_URL = os.getenv("KOYEB_URL")  # Koyeb deployment URL

# Instagram credentials (optional for cookies login)
INSTAGRAM_USERNAME = os.getenv('INSTAGRAM_USERNAME')
INSTAGRAM_PASSWORD = os.getenv('INSTAGRAM_PASSWORD')

# Initialize the bot
bot = telebot.TeleBot(API_TOKEN)

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
        member = bot.get_chat_member(CHANNEL_ID, user_id)
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

# Function to download media from various platforms using yt-dlp
def download_media(url):
    logging.info(f"Attempting to download media from URL: {url}")

    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',  # Combine best video and audio
        'outtmpl': f'{output_dir}%(title)s.%(ext)s',  # Save with original title
        'noplaylist': True,  # Avoid playlists for simplicity
        'socket_timeout': 60,
        'cookies': cookies_file if 'instagram.com' in url else None,  # Load cookies for Instagram
    }

    if 'instagram.com' in url:
        ydl_opts.update({
            'username': INSTAGRAM_USERNAME,
            'password': INSTAGRAM_PASSWORD,
        })

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            final_file_path = ydl.prepare_filename(info_dict)
        return final_file_path
    except Exception as e:
        logging.error(f"yt-dlp download error: {str(e)}")
        raise

# Function to download media and send it asynchronously with progress
def download_and_send(message, url):
    try:
        bot.reply_to(message, "Downloading media, this may take some time...")

        with ThreadPoolExecutor(max_workers=5) as executor:
            future = executor.submit(download_media, url)
            file_path = future.result()

            with open(file_path, 'rb') as media:
                if file_path.lower().endswith(('.mp4', '.mkv', '.webm')):
                    bot.send_video(message.chat.id, media)
                elif file_path.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                    bot.send_photo(message.chat.id, media)
                else:
                    bot.send_document(message.chat.id, media)

            os.remove(file_path)

    except Exception as e:
        bot.reply_to(message, f"Failed to download. Error: {str(e)}")
        logging.error(f"Download failed: {e}")

# Function to run tasks after admin verification
def run_task(message):
    try:
        url = message.text
        user_id = message.from_user.id
        status = check_user_status(user_id)

        if status == 'admin':
            bot.reply_to(message, "Admin verification successful. Starting download...")
            download_and_send(message, url)
        elif status == 'member':
            bot.reply_to(message, "Hello Member! You cannot start this task. Please contact an admin.")
        elif status == 'banned':
            bot.reply_to(message, "You are banned from the channel.")
        elif status == 'not_member':
            bot.reply_to(message, f"Please join the channel first: {CHANNEL_ID}")
        else:
            bot.reply_to(message, "There was an error checking your status. Please try again later.")
    except Exception as e:
        bot.reply_to(message, f"Failed to run task. Error: {str(e)}")
        logging.error(f"Task execution failed: {e}")

# Flask app setup
app = Flask(__name__)
app.config['DEBUG'] = True

# Bot commands and handlers
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Welcome! Paste the link of the content you want to download.")

# Handle media links
@bot.message_handler(func=lambda message: True)
def handle_links(message):
    url = message.text
    threading.Thread(target=run_task, args=(message,)).start()

# Flask routes for webhook handling
@app.route('/' + API_TOKEN, methods=['POST'])
def getMessage_bot():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "!", 200

@app.route('/')
def webhook():
    bot.remove_webhook()
    retries = 3
    while retries > 0:
        try:
            webhook_url = f'https://{KOYEB_URL}/{API_TOKEN}'
            bot.set_webhook(url=webhook_url, timeout=60)
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
