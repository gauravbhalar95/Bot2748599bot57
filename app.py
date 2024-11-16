import os
import logging
import threading
from flask import Flask, request
import telebot
import yt_dlp
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

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

# Function to validate URLs
def is_valid_url(url):
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

# Function to create an inline keyboard for resolution selection
def create_resolution_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("480p", callback_data="480"),
        InlineKeyboardButton("720p", callback_data="720"),
        InlineKeyboardButton("1080p", callback_data="1080"),
        InlineKeyboardButton("2160p (4K)", callback_data="2160")
    )
    return keyboard

# Function to handle resolution selection
@bot2.callback_query_handler(func=lambda call: True)
def handle_resolution_selection(call):
    resolution = call.data
    message = call.message
    url = message.reply_to_message.text  # Retrieve the original URL from the message

    ydl_opts = {
        'format': f'bestvideo[height<={resolution}]+bestaudio/best[height<={resolution}]',
        'outtmpl': f'{output_dir}{sanitize_filename("%(title)s")}.%(ext)s',
        'cookiefile': cookies_file,
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }],
        'socket_timeout': 10,
        'retries': 5,
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.85 Safari/537.36'
    }

    bot2.send_message(call.message.chat.id, f"Downloading in {resolution}p... Please wait.")
    threading.Thread(target=download_and_send, args=(message, url, None, None, ydl_opts)).start()

# Modified download_and_send function to accept ydl_opts as parameter
def download_and_send(message, url, username=None, password=None, ydl_opts=None):
    if not is_valid_url(url):
        bot2.reply_to(message, "The provided URL is not valid. Please enter a valid URL.")
        return

    try:
        bot2.reply_to(message, "Preparing download options...")
        logging.debug("Initiating media download")

        with ThreadPoolExecutor(max_workers=3) as executor:
            future = executor.submit(download_media, url, username, password, ydl_opts)
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
        bot2.reply_to(message, f"Failed to download. Error: {str(e)}")
        logging.error(f"Download failed: {e}")

# Updated handle_links function to show the inline keyboard
@bot2.message_handler(func=lambda message: True)
def handle_links(message):
    url = message.text

    if is_valid_url(url):
        bot2.reply_to(message, "Please select the resolution:", reply_markup=create_resolution_keyboard())
    else:
        bot2.reply_to(message, "The provided URL is not valid. Please enter a valid URL.")

# Flask app setup (same as before)
app = Flask(__name__)

# Flask routes for webhook handling (same as before)
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080, debug=True)