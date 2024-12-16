import os
import logging
from flask import Flask, request
import telebot
import yt_dlp
import re
from mega import Mega  # Mega.nz Python library
from urllib.parse import urlparse

# API Token and Channel ID
API_TOKEN_2 = os.getenv('API_TOKEN_2')
CHANNEL_ID = os.getenv('CHANNEL_ID')  # Your channel ID like '@YourChannel'

# Initialize the bot
bot2 = telebot.TeleBot(API_TOKEN_2, parse_mode='HTML')

# Directory for downloads
output_dir = 'downloads/'
cookies_file = 'cookies.txt'

# Create the download directory if it doesn't exist
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# Logging configuration
logging.basicConfig(level=logging.DEBUG)

# Supported domains for URL validation
SUPPORTED_DOMAINS = ['youtube.com', 'youtu.be', 'instagram.com', 'x.com', 'facebook.com']

# Mega client (initialized after login)
mega_client = None

# Function to sanitize filenames to avoid invalid characters
def sanitize_filename(filename, max_length=250):
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)  # Remove invalid characters
    return filename.strip()[:max_length]

# Check if URL is valid
def is_valid_url(url):
    try:
        result = urlparse(url)
        return result.scheme in ['http', 'https'] and any(domain in result.netloc for domain in SUPPORTED_DOMAINS)
    except ValueError:
        return False

# Download media from URL with optional start and end time for trimming
def download_media(url, start_time=None, end_time=None):
    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'outtmpl': f'{output_dir}{sanitize_filename("%(title)s")}.%(ext)s',
        'cookiefile': cookies_file,
        'postprocessors': [{'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'}],
        'socket_timeout': 10,
        'retries': 5,
    }

    # Apply trimming if start and end times are specified
    if start_time and end_time:
        ydl_opts['postprocessors'].append({
            'key': 'FFmpegVideoConvertor',
            'preferredformat': 'mp4',
            'ffmpeg_args': ['-ss', str(start_time), '-to', str(end_time)]
        })

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info_dict)
        return file_path
    except Exception as e:
        logging.error("Error downloading with yt-dlp", exc_info=True)
        raise

# Upload file to Mega
def upload_to_mega(file_path):
    if mega_client is None:
        raise Exception("Mega client is not logged in. Please use /meganz <username> <password>.")

    try:
        file = mega_client.upload(file_path)
        return file
    except Exception as e:
        logging.error("Error uploading to Mega", exc_info=True)
        raise

# Mega login handler with /meganz command
@bot2.message_handler(commands=['meganz'])
def handle_mega_login(message):
    try:
        # /meganz <username> <password> format expected
        args = message.text.split(maxsplit=2)
        if len(args) < 3:
            bot2.reply_to(message, "Usage: /meganz <username> <password>")
            return

        username = args[1]
        password = args[2]

        # Login to Mega
        global mega_client
        mega_client = Mega().login(username, password)
        bot2.reply_to(message, "Successfully logged into Mega!")

    except Exception as e:
        bot2.reply_to(message, f"Login failed: {str(e)}")

# Download and upload to Mega with trimming
def download_and_upload_to_mega(message, url, start_time=None, end_time=None):
    if not is_valid_url(url):
        bot2.reply_to(message, "Invalid or unsupported URL. Supported platforms: YouTube, Instagram, Twitter, Facebook.")
        return

    try:
        bot2.reply_to(message, "Downloading the video, please wait...")
        file_path = download_media(url, start_time, end_time)

        # Upload to Mega if client is logged in
        mega_link = None
        if mega_client:
            mega_file = upload_to_mega(file_path)
            mega_link = mega_file['link']

        # Send Mega link if uploaded
        if mega_link:
            bot2.reply_to(message, f"Video has been uploaded to Mega: {mega_link}")

        # Send the video directly to the bot if not uploading to Mega
        bot2.send_video(message.chat.id, open(file_path, 'rb'))

        # Clean up downloaded file
        os.remove(file_path)
        bot2.reply_to(message, "Download completed.")
    except Exception as e:
        logging.error("Error during download or upload to Mega", exc_info=True)
        bot2.reply_to(message, f"Download or upload to Mega failed: {str(e)}")

# Telegram command handler when a URL is sent with optional start and end time for trimming
@bot2.message_handler(commands=['mega'])
def handle_mega(message):
    try:
        # /mega <URL> <start_time> <end_time> format expected
        args = message.text.split(maxsplit=3)
        if len(args) < 2:
            bot2.reply_to(message, "Usage: /mega <URL> <start_time> <end_time>")
            return

        url = args[1]
        start_time = None
        end_time = None

        # If start and end time are provided, use them for trimming
        if len(args) == 4:
            start_time, end_time = map(int, args[2].split(':'))
            end_time = int(args[3].split(':')[0])

        # Download and upload to Mega with trimming if specified
        download_and_upload_to_mega(message, url, start_time, end_time)

    except IndexError:
        bot2.reply_to(message, "Please provide a valid URL after the command: /mega <URL> <start_time> <end_time>.")

# Handle direct URL messages (no command)
@bot2.message_handler(func=lambda message: is_valid_url(message.text))
def handle_direct_url(message):
    url = message.text.strip()
    try:
        bot2.reply_to(message, "Downloading the media, please wait...")
        # Direct download and send video
        file_path = download_media(url)

        # Send the media directly to the bot
        bot2.send_video(message.chat.id, open(file_path, 'rb'))

        # Clean up downloaded file
        os.remove(file_path)
        bot2.reply_to(message, "Download completed.")
    except Exception as e:
        logging.error("Error during direct download", exc_info=True)
        bot2.reply_to(message, f"Download failed: {str(e)}")

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
    # Run Flask app
    app.run(host='0.0.0.0', port=8080, debug=True)