import os
import logging
import threading
from flask import Flask, request
import telebot
import yt_dlp
from concurrent.futures import ThreadPoolExecutor
import subprocess

# Load API tokens and channel IDs from environment variables
API_TOKEN_2 = os.getenv('API_TOKEN_2')
CHANNEL_ID = os.getenv('CHANNEL_ID')  # Your Channel ID with @ like '@YourChannel'
KOYEB_URL = os.getenv('KOYEB_URL')

# Initialize the bot with debug mode enabled
bot2 = telebot.TeleBot(API_TOKEN_2, parse_mode='HTML')
telebot.logger.setLevel(logging.DEBUG)

# Directory to save downloaded files
output_dir = 'downloads/'
cookies_file = 'cookies.txt'  # YouTube cookies file

# Create the downloads directory if it does not exist
if not os.path.exists(output_dir):
    os.makedirs(output_dir)
    os.chmod(output_dir, 0o777)  # Set full permissions to avoid permission issues

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

# Function to update yt-dlp using subprocess
def update_yt_dlp():
    try:
        subprocess.run(['yt-dlp', '-U'], check=True)
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to update yt-dlp: {e}")

# Function to sanitize filenames
def sanitize_filename(filename, max_length=200):
    import re
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)
    return filename.strip()[:max_length]

# Function to download media
def download_media(url, username=None, password=None):
    logging.debug(f"Attempting to download media from URL: {url}")

    # Set up options for yt-dlp
    ydl_opts = {
        'format': 'best[ext=mp4]/best',  # Try mp4 format first
        'outtmpl': f'{output_dir}%(title)s.%(ext)s',
        'cookiefile': cookies_file,
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }],
        'socket_timeout': 15,
    }

    # Instagram login
    if username and password:
        ydl_opts['username'] = username
        ydl_opts['password'] = password

    if 'instagram.com' in url:
        logging.debug("Processing Instagram URL")
    elif 'twitter.com' in url or 'x.com' in url:
        logging.debug("Processing Twitter/X URL")
    elif 'youtube.com' in url or 'youtu.be' in url:
        logging.debug("Processing YouTube URL")
    elif 'facebook.com' in url:
        logging.debug("Processing Facebook URL")
    else:
        logging.error(f"Unsupported URL: {url}")
        raise Exception("Unsupported URL!")

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info_dict)
        return file_path
    except KeyError as e:
        if str(e) == "'config'":
            logging.error(f"Extractor error: {e}")
            raise Exception("Extractor error: possibly an issue with yt-dlp or the site.")
        else:
            raise
    except Exception as e:
        logging.error(f"yt-dlp download error: {str(e)}")
        raise

# Function to download media and send it asynchronously
def download_and_send(message, url, username=None, password=None):
    try:
        bot2.reply_to(message, "Downloading media, this may take some time...")

        with ThreadPoolExecutor(max_workers=3) as executor:
            future = executor.submit(download_media, url, username, password)
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

# Function to handle messages
@bot2.message_handler(func=lambda message: True)
def handle_links(message):
    url = message.text

    # Extract Instagram credentials if provided in the message
    username = None
    password = None
    if "@" in url:  # Example: url containing "username:password"
        try:
            username, password = url.split('@', 1)  # Assuming format: username:password@url
            url = password  # Change url to actual URL
        except ValueError:
            bot2.reply_to(message, "Invalid format for Instagram credentials. Please use 'username:password@url'.")
            return

    # Start a new thread for the task to avoid blocking the bot
    threading.Thread(target=download_and_send, args=(message, url, username, password)).start()

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
       
 # Set webhook dynamically using KOYEB_URL from environment
    webhook_url = f'{KOYEB_URL}/{API_TOKEN_2}'
    bot2.set_webhook(url=webhook_url, timeout=60)
    
    return f"Webhook set to {webhook_url}", 200

if __name__ == "__main__":
    # Ensure yt-dlp is updated
    update_yt_dlp()

    # Run the Flask app on a non-privileged port
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 8080)), debug=True)
