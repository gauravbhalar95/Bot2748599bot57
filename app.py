import os
import logging
import tempfile
import threading
from flask import Flask, request
import telebot
import instaloader
import yt_dlp
from concurrent.futures import ThreadPoolExecutor
from moviepy.editor import VideoFileClip
from urllib.parse import urlparse

API_TOKEN_2 = os.getenv('API_TOKEN_2')
CHANNEL_ID = os.getenv('channel')  # Your Channel ID with @, like '@YourChannel'

bot2 = telebot.TeleBot(API_TOKEN_2, parse_mode='HTML')
telebot.logger.setLevel(logging.DEBUG)
cookies_file = 'cookies.txt'  # YouTube cookies file

logging.basicConfig(level=logging.DEBUG)

def is_valid_url(url):
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

def is_user_in_channel(user_id):
    try:
        member = bot2.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logging.error(f"Error checking channel membership: {e}")
        return False

def sanitize_filename(filename, max_length=200):
    import re
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)  # Remove invalid characters
    return filename.strip()[:max_length]

def get_ydl_opts(temp_dir):
    return {
        'format': 'best[ext=mp4]/best',
        'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
        'cookiefile': cookies_file,
        'postprocessors': [{'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'}],
        'socket_timeout': 10,
        'retries': 3,
        'quiet': True,
        'concurrent_fragment_downloads': 5,
        'noprogress': True,
    }

def download_media(url, temp_dir, username=None, password=None):
    logging.debug(f"Attempting to download media from URL: {url}")
    ydl_opts = get_ydl_opts(temp_dir)
    if username and password:
        ydl_opts['username'] = username
        ydl_opts['password'] = password

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info_dict)
        return file_path
    except Exception as e:
        logging.error(f"yt-dlp download error: {str(e)}")
        raise

def download_instagram_image(url, temp_dir):
    loader = instaloader.Instaloader(download_videos=False, save_metadata=False)
    loader.dirname_pattern = temp_dir  # Set download directory to temp_dir
    shortcode = url.split("/")[-2]
    try:
        post = instaloader.Post.from_shortcode(loader.context, shortcode)
        image_path = os.path.join(temp_dir, f"{post.shortcode}.jpg")
        loader.download_pic(image_path, post.url, post.date_utc)
        return image_path
    except Exception as e:
        logging.error(f"Error downloading Instagram image: {e}")
        raise Exception("Failed to download Instagram image")

def trim_video(file_path, start_time, end_time):
    trimmed_path = os.path.join(os.path.dirname(file_path), "trimmed_" + os.path.basename(file_path))
    start_seconds = sum(int(x) * 60 ** i for i, x in enumerate(reversed(start_time.split(":"))))
    end_seconds = sum(int(x) * 60 ** i for i, x in enumerate(reversed(end_time.split(":"))))
    with VideoFileClip(file_path) as video:
        trimmed_video = video.subclip(start_seconds, end_seconds)
        trimmed_video.write_videofile(trimmed_path, codec="libx264")
    return trimmed_path

def download_and_send(message, url, start_time=None, end_time=None, username=None, password=None):
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            bot2.reply_to(message, "Downloading media, this may take some time...")
            with ThreadPoolExecutor(max_workers=5) as executor:
                future = executor.submit(download_media, url, temp_dir, username, password)
                file_path = future.result()
                if start_time and end_time:
                    file_path = trim_video(file_path, start_time, end_time)
                with open(file_path, 'rb') as media:
                    bot2.send_video(message.chat.id, media)
        except Exception as e:
            bot2.reply_to(message, f"Failed to download. Error: {str(e)}")
            logging.error(f"Download failed: {e}")

@bot2.message_handler(func=lambda message: True)
def handle_links(message):
    if not is_user_in_channel(message.from_user.id):
        bot2.reply_to(message, f"Please join our channel to use this bot: {CHANNEL_ID}")
        return
    text = message.text.split()
    url = text[0]
    if not is_valid_url(url):
        bot2.reply_to(message, "The provided URL is not valid. Please enter a valid URL.")
        return
    if "instagram.com" in url:
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                bot2.reply_to(message, "Downloading Instagram image, this may take some time...")
                image_path = download_instagram_image(url, temp_dir)
                with open(image_path, 'rb') as image:
                    bot2.send_photo(message.chat.id, image)
            except Exception as e:
                bot2.reply_to(message, f"Failed to download Instagram image. Error: {str(e)}")
                logging.error(f"Instagram download failed: {e}")
        return

    start_time = text[1] if len(text) > 1 else None
    end_time = text[2] if len(text) > 2 else None
    threading.Thread(target=download_and_send, args=(message, url, start_time, end_time)).start()

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