import os
import logging
import subprocess
from flask import Flask, request
import telebot
import yt_dlp
import re
from urllib.parse import urlparse, parse_qs
from mega import Mega  # Mega.nz Python library

# Load environment variables
API_TOKEN_2 = os.getenv('API_TOKEN_2')
CHANNEL_ID = os.getenv('CHANNEL_ID')  # Example: '@YourChannel'
KOYEB_URL = os.getenv('KOYEB_URL')  # Koyeb URL for webhook

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
def download_media(url, start_time=None, end_time=None, download_playlist=False, format='best[ext=mp4]/best', custom_output_dir=None):
    ydl_opts = {
        'format': format,
        'outtmpl': f'{custom_output_dir or output_dir}{sanitize_filename("%(title)s")}.%(ext)s',
        'cookiefile': cookies_file,
        'postprocessors': [{'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'}],
        'socket_timeout': 10,
        'retries': 5,
        'noplaylist': not download_playlist,  # Whether to download entire playlist or single video
        'postprocessor_args': ['-ss', start_time, '-to', end_time] if start_time and end_time else [],
        'writethumbnail': True,  # Download the thumbnail
        'writeinfojson': True,   # Save metadata
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info_dict)
        return file_path
    except Exception as e:
        logging.error("yt-dlp download error", exc_info=True)
        raise


# Extract video/audio metadata (resolution, duration, etc.)
def get_video_metadata(url):
    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'quiet': True,  # Suppress unnecessary output
        'extractaudio': True,  # Extract audio as well
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            metadata = {
                'title': info_dict.get('title', ''),
                'duration': info_dict.get('duration', 0),
                'formats': info_dict.get('formats', []),
                'url': info_dict.get('url', ''),
            }
        return metadata
    except Exception as e:
        logging.error("yt-dlp metadata extraction error", exc_info=True)
        raise


# Compress video before sending
def compress_video(file_path):
    compressed_file_path = file_path.replace('.mp4', '_compressed.mp4')
    subprocess.run(['ffmpeg', '-i', file_path, '-vcodec', 'libx264', '-crf', '28', compressed_file_path])
    return compressed_file_path


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


# Download file from Mega.nz
def download_from_mega(file_url):
    if mega_client is None:
        raise Exception("Mega client is not logged in. Use /meganz <username> <password> to log in.")

    try:
        file = mega_client.get_file(file_url)
        file_path = os.path.join(output_dir, sanitize_filename(file.name))
        mega_client.download(file, file_path)
        return file_path
    except Exception as e:
        logging.error("Error downloading from Mega", exc_info=True)
        raise


# List files in Mega.nz account
def list_mega_files():
    if mega_client is None:
        raise Exception("Mega client is not logged in. Use /meganz <username> <password> to log in.")

    try:
        files = mega_client.get_files()
        file_list = "\n".join([f"{file['name']} - {file['size']} bytes" for file in files])
        return file_list if file_list else "No files found."
    except Exception as e:
        logging.error("Error listing files on Mega", exc_info=True)
        raise


# Logout from Mega.nz
def logout_from_mega():
    global mega_client
    if mega_client:
        mega_client.logout()
        mega_client = None
        return "Successfully logged out from Mega.nz."
    return "No active Mega session."


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

        # Compress the video
        compressed_file_path = compress_video(file_path)

        # Check file size, if it's above the Telegram limit, upload to Mega
        if os.path.getsize(compressed_file_path) > 50 * 1024 * 1024:  # If greater than 50MB
            if upload_to_mega_flag:
                bot2.reply_to(message, "File is too large for Telegram. Uploading to Mega.nz...")
                mega_link = upload_to_mega(compressed_file_path)
                bot2.reply_to(message, f"Video has been uploaded to Mega.nz: {mega_link}")
            else:
                bot2.reply_to(message, "The file is too large for direct sending. Please consider using Mega for sharing.")
        else:
            # Send video directly if the file size is within limits
            with open(compressed_file_path, 'rb') as video:
                bot2.send_video(message.chat.id, video)

        # Cleanup
        os.remove(file_path)
        os.remove(compressed_file_path)
    except Exception as e:
        logging.error("Download or upload failed", exc_info=True)
        bot2.reply_to(message, f"Download or upload failed: {str(e)}")


# Mega login command
@bot2.message_handler(commands=['meganz'])
def handle_mega_login(message):
    try:
        args = message.text.split(maxsplit=2)
        if len(args) < 3:
            bot2.reply_to(message, "Usage: /meganz <username> <password>")
            return

        username = args[1]
        password = args[2]

        global mega_client
        # Log in to Mega using provided credentials
        mega_client = Mega().login(username, password)
        bot2.reply_to(message, "Successfully logged in to Mega.nz!")
    except Exception as e:
        bot2.reply_to(message, f"Login failed: {str(e)}")


# Mega file list command
@bot2.message_handler(commands=['list_mega'])
def handle_list_files(message):
    try:
        file_list = list_mega_files()
        bot2.reply_to(message, f"Files in your Mega account:\n{file_list}")
    except Exception as e:
        bot2.reply_to(message, f"Failed to list files: {str(e)}")


# Mega file download command
@bot2.message_handler(commands=['download_mega'])
def handle_download_mega(message):
    try:
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            bot2.reply_to(message, "Usage: /download_mega <file_url>")
            return

        file_url = args[1]
        file_path = download_from_mega(file_url)
        bot2.reply_to(message, f"File downloaded to {file_path}")
    except Exception as e:
        bot2.reply_to(message, f"Failed to download file: {str(e)}")


# Mega logout command
@bot2.message_handler(commands=['logout_mega'])
def handle_logout_mega(message):
    try:
        logout_message = logout_from_mega()
        bot2.reply_to(message, logout_message)
    except Exception as e:
        bot2.reply_to(message, f"Logout failed: {str(e)}")


# Download and upload to Mega.nz
@bot2.message_handler(commands=['mega'])
def handle_mega(message):
    try:
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            bot2.reply_to(message, "Usage: /mega <URL>")
            return

        url = args[1]
        handle_download_and_upload(message, url, upload_to_mega_flag=True)
    except IndexError:
        bot2.reply_to(message, "Please provide a valid URL after the command: /mega <URL>.")


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