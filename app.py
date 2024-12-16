import os
import logging
import threading
from flask import Flask, request
import telebot
import yt_dlp
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
import subprocess
import re

# Mega SDK library
from mega import Mega

# Load API tokens and channel IDs from environment variables
API_TOKEN_2 = os.getenv('API_TOKEN_2')
CHANNEL_ID = os.getenv('CHANNEL_ID')  # Your Channel ID with @ like '@YourChannel'

# Initialize the bot with debug mode enabled
bot2 = telebot.TeleBot(API_TOKEN_2, parse_mode='HTML')
telebot.logger.setLevel(logging.DEBUG)

# Directory to save downloaded files
output_dir = 'downloads/'

# Ensure the downloads directory exists
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

# Mega.nz login credentials
mega_client = Mega()
mega_session = None  # Store the session after login


# Command to log in to Mega.nz
@bot2.message_handler(commands=['meganz'])
def mega_login(message):
    try:
        credentials = message.text.split(maxsplit=1)[1]
        email, password = credentials.split()
        global mega_session
        mega_session = mega_client.login(email, password)
        bot2.reply_to(message, "Mega.nz login successful.")
    except Exception as e:
        logging.error(f"Mega.nz login failed: {e}")
        bot2.reply_to(message, f"Failed to log in to Mega.nz. Ensure the format is `/meganz email password`.")


# Command to download a file from Mega.nz
@bot2.message_handler(commands=['mega'])
def mega_download(message):
    if not mega_session:
        bot2.reply_to(message, "Please log in to Mega.nz first using `/meganz email password`.")
        return

    try:
        link = message.text.split(maxsplit=1)[1]
        file = mega_session.download_url(link, dest_path=output_dir)
        bot2.reply_to(message, f"Download completed: {file}")
        with open(file, 'rb') as f:
            bot2.send_document(message.chat.id, f)
        os.remove(file)
    except Exception as e:
        logging.error(f"Mega.nz download failed: {e}")
        bot2.reply_to(message, f"Failed to download file from Mega.nz. Error: {str(e)}")


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