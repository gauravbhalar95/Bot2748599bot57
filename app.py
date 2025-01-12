import os
import logging
from flask import Flask, request
from telebot import TeleBot, types
import telebot
import yt_dlp
import re
import subprocess
from urllib.parse import urlparse, parse_qs
from mega import Mega
import time
import json

# Load environment variables
API_TOKEN_2 = os.getenv('API_TOKEN_2')
CHANNEL_ID = os.getenv('CHANNEL_ID')  # Example: '@YourChannel'
KOYEB_URL = os.getenv('KOYEB_URL')  # Koyeb URL for webhook

# Define commands
commands = [
    types.BotCommand("/mega", "Show Mega options"),
]
bot.set_my_commands(commands)

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
        bot2.reply_to(message, "Invalid or unsupported URL. Supported platforms: YouTube, Instagram, Twitter, Facebook.")
        return

    try:
        bot2.reply_to(message, "Downloading the video, please wait...")

        # Extract start and end times if provided in the YouTube URL
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        start_time = query_params.get('start', [None])[0]
        end_time = query_params.get('end', [None])[0]

        # Download media
        file_path = download_media(url, start_time, end_time)

        if upload_to_mega_flag:
            # Upload to Mega.nz
            bot2.reply_to(message, "Uploading the video to Mega.nz, please wait...")
            mega_link = upload_to_mega(file_path)
            bot2.reply_to(message, f"Video has been uploaded to Mega.nz: {mega_link}")
        else:
            # Send video directly
            with open(file_path, 'rb') as video:
                bot2.send_video(message.chat.id, video)

        # Cleanup
        os.remove(file_path)
    except Exception as e:
        logging.error("Download or upload failed", exc_info=True)
        bot2.reply_to(message, f"Download or upload failed: {str(e)}")


# Mega login command with retries and error handling
@bot2.message_handler(commands=['meganz'])
def handle_mega_login(message):
    global mega_client
    try:
        args = message.text.split(maxsplit=2)
        if len(args) == 1:
            # Perform anonymous login if no email and password are provided
            mega_client = Mega().login()  # Anonymous login
            bot2.reply_to(message, "Logged in to Mega.nz anonymously!")
        elif len(args) == 3:
            # Perform login using email and password with retries
            email = args[1]
            password = args[2]
            retries = 3
            for attempt in range(retries):
                try:
                    mega_client = Mega().login(email, password)
                    bot2.reply_to(message, "Successfully logged in to Mega.nz!")
                    break  # Exit the loop if login is successful
                except Exception as e:
                    if "Expecting value" in str(e):
                        bot2.reply_to(message, f"Login attempt {attempt + 1} failed: Invalid server response. Retrying...")
                        time.sleep(5)  # Wait 5 seconds before retrying
                    else:
                        bot2.reply_to(message, f"Login attempt {attempt + 1} failed: {str(e)}")
                        break  # Exit the loop if it's not a JSONDecodeError
        else:
            bot2.reply_to(message, "Usage: /meganz <username> <password> or /meganz for anonymous login")

    except Exception as e:
        bot2.reply_to(message, f"Login failed: {str(e)}")


@bot2.message_handler(commands=['mega'])
def handle_mega(message):
    try:
        args = message.text.split(maxsplit=2)
        if len(args) < 2:
            bot2.reply_to(message, "Usage: /mega <URL> [<FOLDER_NAME>]")
            return

        url = args[1]
        folder_name = args[2] if len(args) > 2 else None

        # Validate the URL
        if not is_valid_url(url):
            bot2.reply_to(message, "Invalid or unsupported URL. Supported platforms: YouTube, Instagram, Twitter, Facebook.")
            return

        bot2.reply_to(message, "Downloading the video, please wait...")

        # Download media
        file_path = download_media(url)

        # Handle Mega.nz upload
        if mega_client is None:
            bot2.reply_to(message, "Mega.nz is not logged in. Use /meganz <username> <password> to log in.")
            return

        bot2.reply_to(message, "Uploading the video to Mega.nz, please wait...")

        # Find the folder on Mega.nz
        folder = None
        if folder_name:
            folder = mega_client.find(folder_name)
            if not folder:
                bot2.reply_to(message, f"Folder '{folder_name}' not found. Uploading to the root directory instead.")
                folder = None
            else:
                folder = folder[0]  # Use the first matched folder

        # Upload file
        try:
            if folder:
                uploaded_file = mega_client.upload(file_path, folder)
            else:
                uploaded_file = mega_client.upload(file_path)

            public_link = mega_client.get_upload_link(uploaded_file)
            bot2.reply_to(message, f"Video has been uploaded to Mega.nz: {public_link}")
        finally:
            # Cleanup
            os.remove(file_path)

    except Exception as e:
        logging.error("Error in /mega command", exc_info=True)
        bot2.reply_to(message, f"An error occurred: {str(e)}")

# Direct download without Mega.nz
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
    bot2.remove_webhook()
    bot2.set_webhook(url=KOYEB_URL + '/' + API_TOKEN_2, timeout=60)
    return "Webhook set", 200


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080, debug=True)