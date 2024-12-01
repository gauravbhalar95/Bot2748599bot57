import os
import logging
import threading
from flask import Flask, request
import telebot
import yt_dlp
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, parse_qs
import traceback
import re

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

# Ensure yt-dlp is updated
os.system('yt-dlp -U')

# Supported domains
SUPPORTED_DOMAINS = ['youtube.com', 'youtu.be', 'instagram.com', 'twitter.com', 'facebook.com']

# Function to sanitize filenames
def sanitize_filename(filename, max_length=250):  # Reduce max_length if needed
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)  # Remove invalid characters
    return filename.strip()[:max_length]

# Function to validate URLs
def is_valid_url(url):
    try:
        result = urlparse(url)
        return result.scheme in ['http', 'https'] and any(domain in result.netloc for domain in SUPPORTED_DOMAINS)
    except ValueError:
        return False

# Function to parse time parameters
def parse_time_parameters(message_text):
    try:
        parts = message_text.split()
        url = parts[0]
        start_time = None
        end_time = None

        if len(parts) > 1:
            time_pattern = r'(\d{1,2}:\d{2}:\d{2})'
            matches = re.findall(time_pattern, message_text)
            if len(matches) >= 1:
                start_time = matches[0]
            if len(matches) == 2:
                end_time = matches[1]
        
        return url, start_time, end_time
    except Exception as e:
        logging.error("Error parsing time parameters", exc_info=True)
        return None, None, None

# Function to download and trim media
def download_media(url, start_time=None, end_time=None):
    logging.debug(f"Attempting to download media from URL: {url}")

    ydl_opts = {
        'format': 'best[ext=mp4]/best',  # Try mp4 format first
        'outtmpl': f'{output_dir}{sanitize_filename("%(title)s")}.%(ext)s',  # Use sanitized title
        'cookiefile': cookies_file,  # Use cookie file if required for authentication
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }],
        'socket_timeout': 10,
        'retries': 5,
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.85 Safari/537.36'
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info_dict)

        logging.debug(f"Download completed, file path: {file_path}")

        if start_time or end_time:
            trimmed_file_path = file_path.replace(".mp4", "_trimmed.mp4")
            ffmpeg_cmd = f"ffmpeg -i \"{file_path}\" -ss {start_time or 0} -to {end_time or info_dict['duration']} -c copy \"{trimmed_file_path}\""
            os.system(ffmpeg_cmd)
            os.remove(file_path)
            file_path = trimmed_file_path

        return file_path

    except Exception as e:
        logging.error("yt-dlp download error:", exc_info=True)
        raise

# Function to download media and send it asynchronously
def download_and_send(message, url, start_time=None, end_time=None):
    if not is_valid_url(url):
        bot2.reply_to(message, "The provided URL is either invalid or unsupported. Supported platforms: YouTube, Instagram, Twitter, Facebook.")
        return

    try:
        bot2.reply_to(message, "Downloading media, this may take some time...")
        logging.debug("Initiating media download")

        with ThreadPoolExecutor(max_workers=3) as executor:
            future = executor.submit(download_media, url, start_time, end_time)
            file_path = future.result()

            logging.debug(f"Download completed, file path: {file_path}")

            if file_path.lower().endswith('.mp4'):
                with open(file_path, 'rb') as media:
                    bot2.send_video(message.chat.id, media)
            else:
                with open(file_path, 'rb') as media:
                    if file_path.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                        bot2.send_photo(message.chat.id, media)
                    else:
                        bot2.send_document(message.chat.id, media)

            os.remove(file_path)
            bot2.reply_to(message, "Download and sending completed successfully.")

    except Exception as e:
        logging.error("Download failed:", exc_info=True)
        bot2.reply_to(message, f"Failed to download. Error: {str(e)}")

# Function to handle messages
@bot2.message_handler(func=lambda message: True)
def handle_links(message):
    url, start_time, end_time = parse_time_parameters(message.text)
    if url:
        threading.Thread(target=download_and_send, args=(message, url, start_time, end_time)).start()
    else:
        bot2.reply_to(message, "Invalid input. Please provide a valid URL and optional time parameters (e.g., 'https://youtu.be/qmYGd0V4qJY 01:19:10 01:21:48').")

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
    bot2.set_webhook(url=os.getenv('KOYEB_URL') + '/' + API_TOKEN_2, timeout=60)
    return "Webhook set", 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080, debug=True)