import os
import logging
import threading
from flask import Flask, request
import telebot
import yt_dlp
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
from mega import Mega  # Import Mega API

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

# Global variable for storing Mega credentials
mega_credentials = None

def sanitize_filename(filename, max_length=250):  # Reduce max_length if needed
    import re
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)  # Remove invalid characters
    return filename.strip()[:max_length]

# Function to validate URLs
def is_valid_url(url):
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

# Function to download media
def download_media(url, username=None, password=None):
    logging.debug(f"Attempting to download media from URL: {url}")

    # Set up options for yt-dlp with filename sanitization
    ydl_opts = {
        'format': 'best[ext=mp4]/best',  # Try mp4 format first
        'outtmpl': f'{output_dir}{sanitize_filename("%(title)s")}.%(ext)s',  # Use sanitized title
        'cookiefile': cookies_file,  # Use cookie file if required for authentication
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }],
        'socket_timeout': 10,
        'retries': 5,  # Retry on download errors
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.85 Safari/537.36'
    }

    if username and password:
        ydl_opts['username'] = username
        ydl_opts['password'] = password

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info_dict)

        if not os.path.exists(file_path):
            part_file_path = f"{file_path}.part"
            if os.path.exists(part_file_path):
                os.rename(part_file_path, file_path)
                logging.debug(f"Renamed partial file: {part_file_path} to {file_path}")
            else:
                logging.error(f"Downloaded file not found at path: {file_path}")
                raise Exception("Download failed: File not found after download.")

        return file_path

    except Exception as e:
        logging.error(f"yt-dlp download error: {str(e)}")
        raise

# Function to handle Mega.nz login
def mega_login(username, password):
    global mega_credentials
    mega_credentials = Mega().login(username, password)
    logging.debug("Logged in to Mega.nz successfully")

# Function to upload file to Mega.nz
def upload_to_mega(file_path):
    if mega_credentials is None:
        logging.error("Not logged in to Mega.nz")
        return None

    file = mega_credentials.upload(file_path)
    return file

# Function to download media and send it asynchronously
def download_and_send(message, url, username=None, password=None):
    if not is_valid_url(url):
        bot2.reply_to(message, "The provided URL is not valid. Please enter a valid URL.")
        return

    try:
        bot2.reply_to(message, "Downloading media, this may take some time...")
        logging.debug("Initiating media download")

        with ThreadPoolExecutor(max_workers=3) as executor:
            future = executor.submit(download_media, url, username, password)
            file_path = future.result()

            logging.debug(f"Download completed, file path: {file_path}")

            # Upload to Mega.nz
            uploaded_file = upload_to_mega(file_path)
            if uploaded_file:
                bot2.reply_to(message, f"File uploaded to Mega: {uploaded_file['downloadUrl']}")
            else:
                bot2.reply_to(message, "Failed to upload file to Mega.nz.")

            os.remove(file_path)
            bot2.reply_to(message, "Download and sending completed successfully.")

    except Exception as e:
        bot2.reply_to(message, f"Failed to download. Error: {str(e)}")
        logging.error(f"Download failed: {e}")

# Function to handle commands
@bot2.message_handler(commands=['meganz'])
def handle_mega_login(message):
    # Extract username and password
    text = message.text.strip().split(' ', 2)
    if len(text) == 3:
        username = text[1]
        password = text[2]
        try:
            mega_login(username, password)
            bot2.reply_to(message, "Logged in to Mega.nz successfully.")
        except Exception as e:
            bot2.reply_to(message, f"Failed to log in to Mega.nz. Error: {str(e)}")
            logging.error(f"Mega login failed: {e}")
    else:
        bot2.reply_to(message, "Please provide both username and password in the format: /meganz <username> <password>")

# Function to handle messages with media URLs
@bot2.message_handler(func=lambda message: True)
def handle_links(message):
    url = message.text

    username = None
    password = None
    if "@" in url:
        username, password = url.split('@', 1)
        url = password

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
    bot2.set_webhook(url=os.getenv('KOYEB_URL') + '/' + API_TOKEN_2, timeout=60)
    return "Webhook set", 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080, debug=True)