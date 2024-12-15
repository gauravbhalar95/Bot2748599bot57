import os
import logging
import subprocess
import re
from flask import Flask, request
import telebot
import yt_dlp
from mega import Mega
from urllib.parse import urlparse

# Load API tokens and channel IDs from environment variables
API_TOKEN_2 = os.getenv('API_TOKEN_2')
CHANNEL_ID = os.getenv('CHANNEL_ID')  # Your Channel ID with @ like '@YourChannel'

# Initialize the bot with debug mode enabled
bot2 = telebot.TeleBot(API_TOKEN_2, parse_mode='HTML')
telebot.logger.setLevel(logging.DEBUG)

# Mega.nz credentials
mega_username = None
mega_password = None
mega_client = None

# Directory to save downloaded files
output_dir = 'downloads/'
cookies_file = 'cookies.txt'

# Ensure the downloads directory exists
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

# Ensure yt-dlp is updated
def update_yt_dlp():
    try:
        result = subprocess.run(['yt-dlp', '-U'], capture_output=True, text=True, check=True)
        logging.info(f"yt-dlp update output: {result.stdout}")
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to update yt-dlp: {e.stderr}")
    except FileNotFoundError:
        logging.error("yt-dlp is not installed or not found in PATH.")

update_yt_dlp()

# Supported domains
SUPPORTED_DOMAINS = ['youtube.com', 'youtu.be', 'instagram.com', 'x.com', 'facebook.com']

# Function to sanitize filenames
def sanitize_filename(filename, max_length=250):
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)
    return filename.strip()[:max_length]

# Function to validate URLs
def is_valid_url(url):
    try:
        result = urlparse(url)
        return result.scheme in ['http', 'https'] and any(domain in result.netloc for domain in SUPPORTED_DOMAINS)
    except ValueError:
        return False

# Function to download media
def download_media(url):
    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'outtmpl': f'{output_dir}{sanitize_filename("%(title)s")}.%(ext)s',
        'cookiefile': cookies_file,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info_dict)
        return file_path
    except Exception as e:
        logging.error("yt-dlp download error:", exc_info=True)
        raise

# Function to upload to Mega.nz
def upload_to_mega(file_path):
    global mega_client
    if not mega_client:
        raise ValueError("Mega.nz credentials not set. Use /meganz to set them.")
    try:
        upload = mega_client.upload(file_path)
        return mega_client.get_upload_link(upload)
    except Exception as e:
        logging.error("Mega.nz upload error:", exc_info=True)
        raise

# /meganz command to set credentials
@bot2.message_handler(commands=['meganz'])
def set_mega_credentials(message):
    try:
        global mega_username, mega_password, mega_client
        msg_parts = message.text.split()
        if len(msg_parts) == 3:
            mega_username = msg_parts[1]
            mega_password = msg_parts[2]
            mega_client = Mega().login(mega_username, mega_password)
            bot2.reply_to(message, "Mega.nz credentials updated successfully!")
        else:
            bot2.reply_to(message, "Usage: /meganz <username> <password>")
    except Exception as e:
        bot2.reply_to(message, f"Failed to set Mega.nz credentials: {e}")

# Handle all messages to automatically download and upload
@bot2.message_handler(func=lambda message: True)
def handle_message(message):
    try:
        # Check if the message contains a valid URL
        url = message.text.strip()
        if not is_valid_url(url):
            bot2.reply_to(message, "Please send a valid link from supported platforms.")
            return

        bot2.reply_to(message, "Downloading the file, please wait...")

        # Download the media
        file_path = download_media(url)

        # Notify the user that the upload is starting
        bot2.reply_to(message, "Uploading to Mega.nz, please wait...")

        # Upload the file to Mega.nz
        mega_link = upload_to_mega(file_path)

        # Send the Mega.nz link back to the user
        bot2.reply_to(message, f"File uploaded successfully! Here is the link:\n{mega_link}")

        # Remove the downloaded file after upload
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        logging.error("Error in handling message:", exc_info=True)
        bot2.reply_to(message, f"An error occurred: {e}")

# Flask app setup
app = Flask(__name__)

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
    app.run(host='0.0.0.0', port=8080, debug=True)