import os
import logging
import threading
from flask import Flask, request
import telebot
import yt_dlp
from concurrent.futures import ThreadPoolExecutor
from moviepy.editor import VideoFileClip

# Load API tokens and channel IDs from environment variables
API_TOKEN_2 = os.getenv('API_TOKEN_2')
CHANNEL_ID = os.getenv('CHANNEL_ID')  # Your Channel ID with @ like '@YourChannel'

# Initialize the bot with debug mode enabled
bot2 = telebot.TeleBot(API_TOKEN_2, parse_mode='HTML')
telebot.logger.setLevel(logging.DEBUG)

# Directory to save downloaded files
output_dir = 'downloads/'
cookies_file = 'cookies.txt'  # YouTube cookies file

# Ensure the downloads directory exists
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

# Function to sanitize filenames
def sanitize_filename(filename, max_length=200):
    import re
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)  # Remove invalid characters
    return filename.strip()[:max_length]

# yt-dlp options optimized for high video quality
def get_ydl_opts():
    return {
        'format': 'bestvideo+bestaudio/best',  # Best video and audio quality
        'outtmpl': f'{output_dir}%(title)s.%(ext)s',  # Save path for media files
        'cookiefile': cookies_file,  # Use cookie file if required for authentication
        'postprocessors': [{'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'}],
        'socket_timeout': 10,
        'retries': 3,
        'quiet': True,
        'concurrent_fragment_downloads': 5,
        'noprogress': True,
    }

# Function to trim video based on start and end times with improved quality settings
def trim_video(file_path, start_time, end_time):
    trimmed_path = os.path.join(output_dir, "trimmed_" + os.path.basename(file_path))
    start_seconds = sum(int(x) * 60 ** i for i, x in enumerate(reversed(start_time.split(":"))))
    end_seconds = sum(int(x) * 60 ** i for i, x in enumerate(reversed(end_time.split(":"))))

    with VideoFileClip(file_path) as video:
        trimmed_video = video.subclip(start_seconds, end_seconds)
        # Export with higher bitrate for improved quality
        trimmed_video.write_videofile(trimmed_path, codec="libx264", bitrate="5000k")  # Adjust bitrate as needed

    return trimmed_path

# Function to download media using optimized yt-dlp
def download_media(url, username=None, password=None):
    logging.debug(f"Attempting to download media from URL: {url}")
    ydl_opts = get_ydl_opts()
    if username and password:
        ydl_opts['username'] = username
        ydl_opts['password'] = password

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info_dict)
        return file_path
    except Exception as e:
        logging.error(f"yt-dlp download error: {str(e)}")
        raise

# Function to trim video based on start and end times
def trim_video(file_path, start_time, end_time):
    trimmed_path = os.path.join(output_dir, "trimmed_" + os.path.basename(file_path))
    start_seconds = sum(int(x) * 60 ** i for i, x in enumerate(reversed(start_time.split(":"))))
    end_seconds = sum(int(x) * 60 ** i for i, x in enumerate(reversed(end_time.split(":"))))

    with VideoFileClip(file_path) as video:
        trimmed_video = video.subclip(start_seconds, end_seconds)
        trimmed_video.write_videofile(trimmed_path, codec="libx264")

    return trimmed_path

# Function to handle media download, trimming, and send asynchronously
def download_and_send(message, url, start_time=None, end_time=None, username=None, password=None):
    try:
        bot2.reply_to(message, "Downloading media, this may take some time...")

        with ThreadPoolExecutor(max_workers=5) as executor:
            future = executor.submit(download_media, url, username, password)
            file_path = future.result()

            # Trim video if start and end times are provided
            if start_time and end_time:
                file_path = trim_video(file_path, start_time, end_time)

            # Send the file to the user
            with open(file_path, 'rb') as media:
                bot2.send_video(message.chat.id, media)

            # Clean up by removing the file after sending
            os.remove(file_path)
            logging.debug(f"Deleted file: {file_path}")

    except Exception as e:
        bot2.reply_to(message, f"Failed to download. Error: {str(e)}")
        logging.error(f"Download failed: {e}")

# Function to handle incoming messages with URL and optional start and end times
@bot2.message_handler(func=lambda message: True)
def handle_links(message):
    text = message.text.split()
    url = text[0]

    # Extract optional start and end times
    start_time = text[1] if len(text) > 1 else None
    end_time = text[2] if len(text) > 2 else None

    threading.Thread(target=download_and_send, args=(message, url, start_time, end_time)).start()

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