import os
import logging
import threading
from flask import Flask, request
import telebot
import yt_dlp
from urllib.parse import urlparse
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# Load API tokens and channel IDs from environment variables (if applicable)
API_TOKEN_2 = os.getenv('API_TOKEN_2')
CHANNEL_ID = os.getenv('CHANNEL_ID')  # Your Channel ID with @ like '@YourChannel'

def initialize_bot(api_token, debug_mode=True):
    """Initializes the TeleBot instance with error handling."""
    try:
        bot = telebot.TeleBot(api_token, parse_mode='HTML')
        if debug_mode:
            telebot.logger.setLevel(logging.DEBUG)
        return bot
    except Exception as e:
        logging.error(f"Error initializing bot: {str(e)}")
        return None  # Indicate failure

bot2 = initialize_bot(API_TOKEN_2)  # Attempt initialization

# Directory to save downloaded files (optional)
output_dir = 'downloads/'
cookies_file = 'cookies.txt'  # YouTube cookies file (ensure this exists)
output_format = 'bestvideo+bestaudio/best'  # Default format to download (can be disabled)

# Ensure the downloads directory exists (optional)
if output_dir and not os.path.exists(output_dir):
    os.makedirs(output_dir)

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

# Function to validate URLs
def is_valid_url(url):
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

# Function to inform user about unsupported media formats
def handle_unsupported_format(message):
    bot2.reply_to(message, "Currently, only video downloads are supported. Please provide a video URL.")

# Function to handle messages and process URLs
@bot2.message_handler(func=lambda message: True)
def handle_links(message):
    url = message.text

    if not is_valid_url(url):
        bot2.reply_to(message, "The provided URL is not valid. Please enter a valid URL.")
        return

    # Check if URL potentially points to video content
    if not url.lower().endswith(('.mp4', '.webm', '.avi', '.mkv', '.flv')):
        handle_unsupported_format(message)
        return

    # Download disabled or no output_dir specified, inform user and exit
    if not output_dir:
        bot2.reply_to(message, "Video downloads are currently disabled. Please contact the administrator for more information.")
        return

    try:
        # Delegate download logic to a separate function for clarity
        download_and_send(message, url)
    except Exception as e:
        bot2.reply_to(message, f"Error during processing: {str(e)}")
        logging.error(f"Error during processing: {e}")

# Function to download and send media (optional)
def download_and_send(message, url):
    # Include download logic here if video downloading is enabled
    # (e.g., using yt_dlp with appropriate error handling)

    # Example placeholder message for now
    bot2.reply_to(message, "Video download functionality is currently under development. Stay tuned for future updates!")

# Flask app setup (if using webhook)
app = Flask(__name__)

# Flask routes for webhook handling (if using webhook)
@app.route('/' + API_TOKEN_2, methods=['POST'])
def getMessage_bot2():
    if bot2:  # Check if bot initialization was successful
        bot2.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "!", 200

@app.route('/')
def webhook():
    if bot2:  # Check if bot initialization was successful
        bot2.remove_webhook()
        bot2.set_webhook(url=os.getenv('KOYEB_URL') + '/' + API_TOKEN_2, timeout=60)
    return "Webhook set", 200


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080, debug=True)