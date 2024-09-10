import requests
import os
import telebot
import threading
import logging
from flask import Flask, request

# Bot setup
API_TOKEN_2 = os.getenv('API_TOKEN_2')
bot2 = telebot.TeleBot(API_TOKEN_2)


# Logging setup
logging.basicConfig(level=logging.INFO)

# Flask app setup
app = Flask(__name__)


# Use environment variables for security
INSTAGRAM_USERNAME = os.getenv('INSTAGRAM_USERNAME')
INSTAGRAM_PASSWORD = os.getenv('INSTAGRAM_PASSWORD')

# Download function using yt-dlp
def download_media(url):
    ydl_opts = {
        'format': 'best',
        'outtmpl': f'{output_dir}%(title)s.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }],
        'username': INSTAGRAM_USERNAME,
        'password': INSTAGRAM_PASSWORD,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=True)
        file_path = ydl.prepare_filename(info_dict)

    return file_path

# Function to download and send Instagram media
def download_and_send_instagram_media(message, instagram_url):
    try:
        media_url = fetch_instagram_media(instagram_url)
        if media_url:
            media_response = requests.get(media_url, stream=True)
            media_response.raise_for_status()

            file_extension = media_url.split('.')[-1]
            media_file = f"downloads/media.{file_extension}"

            with open(media_file, 'wb') as f:
                for chunk in media_response.iter_content(chunk_size=1024):
                    f.write(chunk)

            with open(media_file, 'rb') as media:
                if file_extension in ['mp4', 'mkv', 'webm']:
                    bot2.send_video(message.chat.id, media)
                elif file_extension in ['jpg', 'jpeg', 'png', 'gif']:
                    bot2.send_photo(message.chat.id, media)
                else:
                    bot2.send_document(message.chat.id, media)

            os.remove(media_file)
        else:
            bot2.reply_to(message, "Failed to fetch media from Instagram.")
    except Exception as e:
        bot2.reply_to(message, f"Error downloading media: {str(e)}")
        logging.error(f"Error downloading media: {e}")

# Bot command handlers
@bot2.message_handler(commands=['start'])
def send_welcome(message):
    bot2.reply_to(message, "Welcome! Paste the Instagram link of the content you want to download.")

@bot2.message_handler(func=lambda message: True)
def handle_message(message):
    instagram_url = message.text
    bot2.reply_to(message, "Downloading media, please wait...")
    threading.Thread(target=download_and_send_instagram_media, args=(message, instagram_url)).start()

# Flask webhook routes
@app.route('/' + API_TOKEN_2, methods=['POST'])
def webhook_handler():
    bot2.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "OK", 200

@app.route('/')
def webhook():
    bot2.remove_webhook()
    bot2.set_webhook(url='https://bot2-mb9e.onrender.com/' + API_TOKEN_2, timeout=60)
    return "Webhook set", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)
