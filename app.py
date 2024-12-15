import os
import logging
import threading
from flask import Flask, request
import telebot
import yt_dlp
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, parse_qs
import subprocess
import traceback
import re
import time
from mega import Mega  # Mega.nz API for handling Mega operations

# Load API tokens and channel IDs from environment variables
API_TOKEN_2 = os.getenv('API_TOKEN_2')
CHANNEL_ID = os.getenv('CHANNEL_ID')  # Your Channel ID with @ like '@YourChannel'

# Initialize the bot with debug mode enabled
bot2 = telebot.TeleBot(API_TOKEN_2, parse_mode='HTML')
telebot.logger.setLevel(logging.DEBUG)

# Directory to save downloaded files
output_dir = 'downloads/'
cookies_file = 'cookies.txt'  # YouTube cookies file

# Mega.nz login details (to be stored safely)
mega_username = None
mega_password = None

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

# Function to download media (e.g., video) from a URL with retry logic
def download_media(url, start_time=None, end_time=None, retries=5):
    logging.debug(f"Attempting to download media from URL: {url}")

    ydl_opts = {
        'format': 'best[ext=mp4]/best',  # Prefer mp4 format
        'outtmpl': f'{output_dir}{sanitize_filename("%(title)s")}.%(ext)s',  # Use sanitized title for filename
        'cookiefile': cookies_file,  # If needed, use a cookie file for authentication (optional)
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',  # Convert video to mp4 format
            'preferedformat': 'mp4',
        }],
        'socket_timeout': 60,  # Increase the timeout for network requests
        'retries': retries,  # Set the retry limit
        'quiet': False  # Set to False for more detailed logs
    }

    attempt = 0
    while attempt < retries:
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(url, download=True)
                file_path = ydl.prepare_filename(info_dict)
                logging.debug(f"Download completed, file path: {file_path}")

                if start_time or end_time:
                    # Optional: Process video to trim it based on start_time and end_time
                    trimmed_file_path = file_path.replace(".mp4", "_trimmed.mp4")
                    ffmpeg_cmd = f"ffmpeg -i \"{file_path}\" -ss {start_time or 0} -to {end_time or info_dict['duration']} -c copy \"{trimmed_file_path}\""
                    os.system(ffmpeg_cmd)
                    os.remove(file_path)
                    file_path = trimmed_file_path

                return file_path
        except yt_dlp.utils.DownloadError as e:
            logging.error(f"Download failed, attempt {attempt + 1} of {retries}. Error: {str(e)}")
            attempt += 1
            if attempt >= retries:
                logging.error("Max retry attempts reached, download failed.")
                raise
            time.sleep(5)  # Wait before retrying

# Function to handle Mega.nz login
def mega_login():
    global mega_username, mega_password
    if mega_username and mega_password:
        mega = Mega()
        m = mega.login(mega_username, mega_password)
        return m
    return None

# Function to upload files to Mega.nz
def upload_to_mega(file_path):
    try:
        mega = mega_login()
        if not mega:
            logging.error("Mega login failed")
            return None

        logging.info(f"Uploading {file_path} to Mega.nz")
        uploaded_file = mega.upload(file_path)
        return uploaded_file
    except Exception as e:
        logging.error(f"Error uploading file to Mega: {e}", exc_info=True)
        return None

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

            # Upload the file to Mega.nz after sending
            uploaded_file = upload_to_mega(file_path)
            if uploaded_file:
                bot2.reply_to(message, f"File uploaded to Mega.nz: {uploaded_file['public_link']}")
            else:
                bot2.reply_to(message, "Failed to upload to Mega.nz.")

            os.remove(file_path)
            bot2.reply_to(message, "Download and sending completed successfully.")

    except Exception as e:
        logging.error("Download failed:", exc_info=True)
        bot2.reply_to(message, f"Failed to download. Error: {str(e)}")

# Command to set Mega.nz credentials
@bot2.message_handler(commands=['meganz'])
def set_mega_credentials(message):
    global mega_username, mega_password
    try:
        bot2.reply_to(message, "Please provide your Mega.nz username and password in the following format:\n`username password`")
        bot2.register_next_step_handler(message, save_mega_credentials)
    except Exception as e:
        logging.error("Error in /meganz handler:", exc_info=True)
        bot2.reply_to(message, f"Failed to handle the command. Error: {str(e)}")

# Function to save Mega.nz credentials
def save_mega_credentials(message):
    global mega_username, mega_password
    try:
        credentials = message.text.split()
        if len(credentials) == 2:
            mega_username, mega_password = credentials
            bot2.reply_to(message, "Mega.nz credentials saved successfully.")
        else:
            bot2.reply_to(message, "Invalid format. Please send your Mega.nz username and password as `username password`.")
    except Exception as e:
        logging.error("Error saving Mega.nz credentials:", exc_info=True)
        bot2.reply_to(message, "Failed to save Mega.nz credentials.")

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