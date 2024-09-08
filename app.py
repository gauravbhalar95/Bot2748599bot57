# Import libraries
from flask import Flask, request
import telebot
import yt_dlp
import os
import re
import threading
import time

# Bot 2: Media Downloader
API_TOKEN_2 = os.getenv('API_TOKEN_2')
bot2 = telebot.TeleBot(API_TOKEN_2)

# Directory to save downloaded files
output_dir = 'downloads/'
cookies_file = 'cookies.txt'

# Cache dictionary to store recent downloads (optional)
media_cache = {}

# Create the downloads directory if it does not exist
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# Sanitize file names to prevent errors
def sanitize_filename(filename, max_length=100):
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)
    if len(filename) > max_length:
        filename = filename[:max_length]
    return filename

# Download function using yt-dlp
def download_media(url):
    # If media is already cached, return the cached path (optional)
    if url in media_cache:
        return media_cache[url]

    ydl_opts = {
        'format': 'best',
        'outtmpl': f'{output_dir}%(title)s.%(ext)s',
        'cookiefile': cookies_file,
        # Limit download speed to avoid overwhelming the server (optional)
        'throttled-rate': '1M',
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }]
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=True)
        file_path = ydl.prepare_filename(info_dict)
        file_path = sanitize_filename(file_path)

    # Store downloaded file in cache (optional)
    media_cache[url] = file_path
    return file_path

# Function to download media and send it asynchronously
def download_and_send(message, url):
    try:
        file_path = download_media(url)
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

# Flask app setup
app = Flask(__name__)

# Bot 2 commands and handlers
@bot2.message_handler(commands=['start'])
def send_welcome_bot2(message):
    bot2.reply_to(message, "Welcome! Paste the link of the content you want to download.")

# Handle media links
@bot2.message_handler(func=lambda message: True)
def handle_links(message):
    url = message.text
    # Reply immediately to the user
    bot2.reply_to(message, "Downloading media, this may take some time...")
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
    # Replace 'your-render-url' with your actual Render or any other host URL
    bot2.set_webhook(url='https://bot2-mb9e.onrender.com/' + API_TOKEN_2, timeout=60)
    return "Webhook set", 200

if __name__ == "__main__":
    # Run the Flask app
    app.run(host='0.0.0.0', port=5000)
