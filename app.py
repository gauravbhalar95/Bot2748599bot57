# Import libraries
from flask import Flask, request
import telebot
import yt_dlp
import os

# Bot 2: Media Downloader
API_TOKEN_2 = '7511959076:AAFiaIsL8Anb9vcROywHzVJ_FiRYXhtVetQ'
bot2 = telebot.TeleBot(API_TOKEN_2)

# Directory to save downloaded files
output_dir = 'downloads/'

# Path to the cookies file
cookies_file = 'cookies.txt'

# Create the downloads directory if it does not exist
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# Download function using yt-dlp
def download_media(url):
    ydl_opts = {
        'format': 'best',
        'outtmpl': f'{output_dir}%(title)s.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }],
        'cookiefile': cookies_file
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=True)
        file_path = ydl.prepare_filename(info_dict)

    return file_path

# Flask app setup
app = Flask(__name__)

# Bot 2 commands and handlers
@bot2.message_handler(commands=['start'])
def send_welcome_bot2(message):
    bot2.reply_to(message, "Welcome! Paste the link of the content you want to download.")

@bot2.message_handler(func=lambda message: True)
def handle_links(message):
    url = message.text
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

# Flask routes for webhook handling
@app.route('/' + API_TOKEN_2, methods=['POST'])
def getMessage_bot2():
    bot2.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "!", 200

@app.route('/')
def webhook():
    bot2.remove_webhook()
    # Replace 'your-replit-url' with your actual Replit URL
    bot2.set_webhook(url='https://b56b48ec-74b1-45a0-a857-4dcb43b3563d-00-195k50i8quivj.riker.replit.dev/' + API_TOKEN_2)
    return "Webhook set", 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=80)

