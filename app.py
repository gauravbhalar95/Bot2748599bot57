import os
import logging
from flask import Flask, request
import telebot
import yt_dlp
import re
import subprocess
from urllib.parse import urlparse, parse_qs
from mega import Mega
import time
import json
import requests

# Load environment variables
API_TOKEN_2 = os.getenv('BOT_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')
KOYEB_URL = os.getenv('WEBHOOK_URL')

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
SUPPORTED_DOMAINS = ['instagram.com', 'x.com', 'facebook.com', 'youtube.com']  # Added youtube.com

# Mega client
mega_client = None

# File size limit for direct sending (in bytes)
FILE_SIZE_LIMIT = 50 * 1024 * 1024  # 50MB

# Sanitize filenames
def sanitize_filename(filename, max_length=250):
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)
    return filename.strip()[:max_length]

# Check URL validity
def is_valid_url(url):
    try:
        result = urlparse(url)
        return result.scheme in ['http', 'https'] and any(domain in result.netloc for domain in SUPPORTED_DOMAINS)
    except ValueError:
        return False

# Download media with yt-dlp and thumbnail extraction
def download_media(url, start_time=None, end_time=None):
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',  # Prioritize mp4
        'outtmpl': f'{output_dir}{sanitize_filename("%(title)s")}.%(ext)s',
        'cookiefile': cookies_file,
        'postprocessors': [{'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'}],
        'socket_timeout': 10,
        'retries': 5,
        'writesubtitles': False, # Disable subtitles to prevent issues with youtube.com
        'noplaylist': True, # Prevent downloading entire playlists
        'extract_flat': True # Extract single video from playlist or channel
    }

    if start_time and end_time:
        ydl_opts['postprocessor_args'] = ['-ss', start_time, '-to', end_time]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info_dict)

            # Extract thumbnail (try different formats)
            thumbnail_url = info_dict.get('thumbnail')
            if thumbnail_url:
                try:
                    thumb_data = requests.get(thumbnail_url, stream=True).content
                    thumb_path = f'{output_dir}{sanitize_filename("%(title)s")}.jpg'
                    with open(thumb_path, 'wb') as f:
                        f.write(thumb_data)
                    return file_path, thumb_path
                except Exception as e:
                    logging.error("Error downloading thumbnail", exc_info=True)
                    # Continue without thumbnail if it fails
            return file_path, None # Return None if thumbnail download fails

    except Exception as e:
        logging.error("yt-dlp download error", exc_info=True)
        raise

# ... (rest of the code: upload_to_mega, handle_mega_login, handle_mega remains the same)

def handle_download_and_upload(message, url, upload_to_mega_flag):
    if not is_valid_url(url):
        bot2.reply_to(message, "Invalid or unsupported URL. Supported platforms: YouTube, Instagram, Twitter, Facebook.")
        return

    try:
        bot2.reply_to(message, "Downloading the video, please wait...")

        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        start_time = query_params.get('start', [None])[0]
        end_time = query_params.get('end', [None])[0]

        file_path, thumb_path = download_media(url, start_time, end_time)

        file_size = os.path.getsize(file_path)

        if upload_to_mega_flag:  # Mega upload
            bot2.reply_to(message, "Uploading to Mega.nz, please wait...")
            mega_link = upload_to_mega(file_path)
            bot2.reply_to(message, f"Video uploaded to Mega.nz: {mega_link}")
        elif file_size > FILE_SIZE_LIMIT:  # Streaming link or download link
            bot2.reply_to(message, "Video size is too large. Providing a streaming/download link (if available).")
            # Implement logic to generate a streaming link or a temporary download link here.
            # This depends on your server setup and how you want to host the large files.
            # Example (replace with your actual logic):
            # streaming_link = f"https://your-server.com/stream/{os.path.basename(file_path)}"
            # bot2.reply_to(message, f"Stream the video here: {streaming_link}")
            bot2.reply_to(message, "Large file support is not yet implemented. Please use /mega to upload to Mega.nz")
        else:  # Direct send
            with open(file_path, 'rb') as video:
                if thumb_path:
                    with open(thumb_path, 'rb') as thumb:
                        bot2.send_video(message.chat.id, video, thumbnail=thumb)
                    os.remove(thumb_path) # Remove thumbnail after sending
                else:
                    bot2.send_video(message.chat.id, video)

        os.remove(file_path)  # Cleanup

    except Exception as e:
        logging.error("Download or upload failed", exc_info=True)
        bot2.reply_to(message, f"Download or upload failed: {str(e)}")


# ... (rest of the code: /mega command, direct download handler, Flask app, webhook setup remain the same)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080, debug=True)

