import os
import logging
from flask import Flask, request
import telebot
import yt_dlp
import re
import subprocess
from mega import Mega  # Mega.nz Python library

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

# Supported domains
SUPPORTED_DOMAINS = ['youtube.com', 'youtu.be', 'instagram.com', 'x.com', 'facebook.com']

# Mega client (will be initialized later after login)
mega_client = None

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

# Download media
def download_media(url):
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
        return file_path
    except Exception as e:
        logging.error("yt-dlp download error", exc_info=True)
        raise

# Trim video using ffmpeg
def trim_video(input_path, start_time, end_time):
    output_path = f"{output_dir}trimmed_{sanitize_filename(input_path)}"
    try:
        subprocess.run([
            'ffmpeg', '-i', input_path,
            '-ss', start_time, '-to', end_time, '-c:v', 'libx264', '-c:a', 'aac',
            '-strict', 'experimental', output_path
        ], check=True)
        return output_path
    except subprocess.CalledProcessError as e:
        logging.error("FFmpeg error during trimming", exc_info=True)
        raise

# Upload to Mega
def upload_to_mega(file_path):
    if mega_client is None:
        raise Exception("Mega client is not initialized. Please log in first using /meganz <username> <password>.")

    try:
        file = mega_client.upload(file_path)
        return file
    except Exception as e:
        logging.error("Mega upload error", exc_info=True)
        raise

# Download, trim, upload and send media
def download_trim_upload_and_send_media(message, url, start_time, end_time):
    if not is_valid_url(url):
        bot2.reply_to(message, "Invalid or unsupported URL. Supported platforms: YouTube, Instagram, Twitter, Facebook.")
        return

    try:
        bot2.reply_to(message, "Downloading video, please wait...")
        file_path = download_media(url)

        # Trim the video
        if start_time and end_time:
            trimmed_file_path = trim_video(file_path, start_time, end_time)
        else:
            trimmed_file_path = file_path

        # Upload to Mega
        mega_file = upload_to_mega(trimmed_file_path)

        # Send the Mega link back to the user
        mega_link = mega_file['link']
        bot2.reply_to(message, f"Video trimmed successfully! The file has been uploaded to Mega: {mega_link}")

        # Clean up the downloaded and trimmed files
        if start_time and end_time:
            os.remove(trimmed_file_path)
        os.remove(file_path)
        bot2.reply_to(message, "Download, trim and upload completed.")
    except Exception as e:
        logging.error("Download, trim, or upload failed", exc_info=True)
        bot2.reply_to(message, f"Download, trim, or upload failed: {str(e)}")

# Mega login command
@bot2.message_handler(commands=['meganz'])
def handle_mega_login(message):
    try:
        # Expecting the format /meganz <username> <password>
        args = message.text.split(maxsplit=2)
        if len(args) < 3:
            bot2.reply_to(message, "Usage: /meganz <username> <password>")
            return

        username = args[1]
        password = args[2]

        # Log in to Mega
        global mega_client
        mega_client = Mega().login(username, password)
        bot2.reply_to(message, "Successfully logged in to Mega!")

    except Exception as e:
        bot2.reply_to(message, f"Login failed: {str(e)}")

# Telegram command handler for trimming and uploading to Mega
@bot2.message_handler(commands=['trim'])
def handle_trim(message):
    try:
        # Expecting the format /trim <URL> <start_time> <end_time>
        args = message.text.split(maxsplit=3)
        if len(args) < 4:
            bot2.reply_to(message, "Usage: /trim <URL> <start_time> <end_time>")
            return

        url = args[1]
        start_time = args[2]
        end_time = args[3]

        # Handle download, trim, upload to Mega and send media
        download_trim_upload_and_send_media(message, url, start_time, end_time)

    except IndexError:
        bot2.reply_to(message, "Please provide a valid URL, start time, and end time after the command: /trim <URL> <start_time> <end_time>.")

# Telegram command handler for download and upload to Mega
@bot2.message_handler(commands=['mega'])
def handle_mega(message):
    try:
        # Expecting the format /mega <URL>
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            bot2.reply_to(message, "Usage: /mega <URL>")
            return

        url = args[1]
        # Handle download, upload to Mega and send media
        download_trim_upload_and_send_media(message, url, None, None)

    except IndexError:
        bot2.reply_to(message, "Please provide a valid URL after the command: /mega <URL>.")

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
    # Run Flask app to handle incoming webhook requests
    app.run(host='0.0.0.0', port=8080, debug=True)
