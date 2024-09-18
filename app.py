import os
import logging
import threading
from flask import Flask, request
import telebot
import yt_dlp
import requests
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from concurrent.futures import ThreadPoolExecutor

# Load the API token and channel ID from environment variables
API_TOKEN_2 = os.getenv('API_TOKEN_2')
CHANNEL_ID = os.getenv('CHANNEL_ID')  # Load your Telegram channel ID from environment

# Initialize the bot
bot2 = telebot.TeleBot(API_TOKEN_2)

# Directory to save downloaded files
output_dir = 'downloads/'
cookies_file = 'cookies.txt'

# Create the downloads directory if it does not exist
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# Logging setup
logging.basicConfig(level=logging.INFO)

# Sanitize file names to prevent errors
def sanitize_filename(filename, max_length=200):
    import re
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)
    return filename.strip()[:max_length]

# Download image function
def download_image(url):
    response = requests.get(url, stream=True)
    if response.status_code == 200:
        filename = sanitize_filename(url.split('/')[-1])
        file_path = os.path.join(output_dir, filename)
        with open(file_path, 'wb') as file:
            for chunk in response.iter_content(1024):
                file.write(chunk)
        return file_path
    else:
        raise Exception(f"Failed to download image from {url}")

# yt-dlp download options with cookies, including Instagram stories and images
def download_media(url):
    # Check platform-specific options for yt-dlp (YouTube, Instagram, Twitter, etc.)
    # Same as before...
    pass

# Function to download media and send it asynchronously with progress
def download_and_send(message, url):
    try:
        bot2.reply_to(message, "Downloading media, this may take some time...")

        # Use a thread pool executor to manage threads
        with ThreadPoolExecutor(max_workers=3) as executor:
            future = executor.submit(download_media, url)
            file_path = future.result()

            with open(file_path, 'rb') as media:
                if file_path.lower().endswith(('.mp4', '.mkv', '.webm')):
                    bot2.send_video(message.chat.id, media)
                elif file_path.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                    bot2.send_photo(message.chat.id, media)
                else:
                    bot2.send_document(message.chat.id, media)

            os.remove(file_path)

    except Exception as e:
        bot2.reply_to(message, f"Failed to download. Error: {str(e)}")
        logging.error(f"Download failed: {e}")

# Function to check if user is in the required channel
def is_user_in_channel(user_id):
    try:
        status = bot2.get_chat_member(CHANNEL_ID, user_id).status
        return status in ['member', 'administrator', 'creator']
    except Exception as e:
        logging.error(f"Error checking user membership: {e}")
        return False

# Handle the verification process
def verify_membership(message):
    if is_user_in_channel(message.from_user.id):
        bot2.reply_to(message, "Thank you for being a member! You can now use the bot.")
        return True
    else:
        keyboard = InlineKeyboardMarkup()
        join_button = InlineKeyboardButton('Join Channel', url=f'https://t.me/{CHANNEL_ID[1:]}')
        keyboard.add(join_button)
        bot2.reply_to(message, "Please join our channel to use this bot.", reply_markup=keyboard)
        return False

# Flask app setup
app = Flask(__name__)

# Bot 2 commands and handlers
@bot2.message_handler(commands=['start'])
def send_welcome_bot2(message):
    bot2.reply_to(message, "Welcome! Paste the link of the content you want to download after joining our channel.")
    
@bot2.message_handler(func=lambda message: True)
def handle_links(message):
    if verify_membership(message):
        url = message.text
        # Start a new thread for the download to avoid blocking the bot
        threading.Thread(target=download_and_send, args=(message, url)).start()

# Flask routes for webhook handling
@app.route('/' + API_TOKEN_2, methods=['POST'])
def getMessage_bot2():
    bot2.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "!", 200

@app.route('/')
def webhook():
    bot2.remove_webhook()
    bot2.set_webhook(url=f'https://bot2-mb9e.onrender.com/{API_TOKEN_2}', timeout=60)
    return "Webhook set", 200

if __name__ == "__main__":
    # Run the Flask app
    app.run(host='0.0.0.0', port=80)
