from flask import Flask, request
import telebot
import yt_dlp
import os
import re
import asyncio
import logging

API_TOKEN_2 = os.getenv('API_TOKEN_2')
bot2 = telebot.TeleBot(API_TOKEN_2)

output_dir = 'downloads/'
cookies_file = 'cookies.txt'
logging.basicConfig(level=logging.INFO)

if not os.path.exists(output_dir):
    os.makedirs(output_dir)

def sanitize_filename(filename, max_length=100):
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)
    filename = filename.strip()
    if len(filename) > max_length:
        filename = filename[:max_length]
    return filename

def download_media(url):
    ydl_opts = {
        'format': 'best',
        'outtmpl': f'{output_dir}%(title)s.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }],
        'cookiefile': cookies_file,
        'username': os.getenv('IG_USERNAME'),
        'password': os.getenv('IG_PASSWORD')
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=True)
        file_path = ydl.prepare_filename(info_dict)

    return file_path

async def download_and_send_async(message, url):
    try:
        loop = asyncio.get_event_loop()
        file_path = await loop.run_in_executor(None, download_media, url)
        with open(file_path, 'rb') as media:
            if file_path.lower().endswith(('.mp4', '.mkv', '.webm')):
                await bot2.send_video(message.chat.id, media)
            elif file_path.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                await bot2.send_photo(message.chat.id, media)
            else:
                await bot2.send_document(message.chat.id, media)
        os.remove(file_path)
    except Exception as e:
        await bot2.reply_to(message, f"Failed to download. Error: {str(e)}")
        logging.error(f"Download failed: {e}")

@bot2.message_handler(commands=['start'])
def send_welcome_bot2(message):
    bot2.reply_to(message, "Welcome! Paste the link of the content you want to download.")

@bot2.message_handler(func=lambda message: True)
def handle_links(message):
    url = message.text
    bot2.reply_to(message, "Downloading media, this may take some time...")
    asyncio.run(download_and_send_async(message, url))

app = Flask(__name__)

@app.route('/' + API_TOKEN_2, methods=['POST'])
def getMessage_bot2():
    bot2.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "!", 200

@app.route('/')
def webhook():
    bot2.remove_webhook()
    bot2.set_webhook(url='https://bot2-mb9e.onrender.com/' + API_TOKEN_2, timeout=60)
    return "Webhook set", 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=80)
