import os
import logging
import threading
from flask import Flask, request
import telebot
import instaloader
import yt_dlp
from concurrent.futures import ThreadPoolExecutor
from moviepy.editor import VideoFileClip
from urllib.parse import urlparse

# Load API tokens and channel IDs from environment variables
API_TOKEN_2 = os.getenv('API_TOKEN_2')
CHANNEL_ID = os.getenv('channel')  # Your Channel ID with @, like '@YourChannel'

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

# Function to validate URLs
def is_valid_url(url):
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

# Function to check if a user is a member of the required channel
def is_user_in_channel(user_id):
    try:
        member = bot2.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logging.error(f"Error checking channel membership: {e}")
        return False

# Function to sanitize filenames
def sanitize_filename(filename, max_length=200):
    import re
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)  # Remove invalid characters
    return filename.strip()[:max_length]

# yt-dlp options optimized for speed
def get_ydl_opts():
    return {
        'format': 'best[ext=mp4]/best',
        'outtmpl': f'{output_dir}%(title)s.%(ext)s',
        'cookiefile': cookies_file,
        'postprocessors': [{'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'}],
        'socket_timeout': 10,
        'retries': 3,
        'quiet': True,
        'concurrent_fragment_downloads': 5,
        'noprogress': True,
    }

# Function to download media using optimized yt-dlp
def download_media(url, username=None, password=None):
    logging.debug(f"Attempting to download media from URL: {url}")
    ydl_opts = get_ydl_opts()
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

# Function to download Instagram image
def download_instagram_image(url):
    # Ensure the downloads directory exists
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    loader = instaloader.Instaloader(download_videos=False, save_metadata=False)
    
    # Extract shortcode from the URL
    shortcode = url.split("/")[-2]
    try:
        post = instaloader.Post.from_shortcode(loader.context, shortcode)
        image_path = f"{output_dir}{post.shortcode}.jpg"
        
        # Download the image
        loader.download_pic(image_path, post.url, post.date_utc)
        return image_path
    except Exception as e:
        logging.error(f"Error downloading Instagram image: {e}")
        raise Exception("Failed to download Instagram image")

# Function to trim video based on start and end times
def trim_video(file_path, start_time, end_time):
    trimmed_path = os.path.join(output_dir, "trimmed_" + os.path.basename(file_path))
    start_seconds = sum(int(x) * 60 ** i for i, x in enumerate(reversed(start_time.split(":"))))
    end_seconds = sum(int(x) * 60 ** i for i, x in enumerate(reversed(end_time.split(":"))))

    with VideoFileClip(file_path) as video:
        trimmed_video = video.subclip(start_seconds, end_seconds)
        trimmed_video.write_videofile(trimmed_path, codec="libx264")

    return trimmed_path

# Function to handle media download, trimming, and send asynchronously
def download_and_send(message, url, start_time=None, end_time=None, username=None, password=None):
    try:
        bot2.reply_to(message, "Downloading media, this may take some time...")

        with ThreadPoolExecutor(max_workers=5) as executor:
            future = executor.submit(download_media, url, username, password)
            file_path = future.result()

            # Trim video if start and end times are provided
            if start_time and end_time:
                file_path = trim_video(file_path, start_time, end_time)

            # Send the file to the user
            with open(file_path, 'rb') as media:
                bot2.send_video(message.chat.id, media)

            # Clean up by removing the file after sending
            os.remove(file_path)
            logging.debug(f"Deleted file: {file_path}")

    except Exception as e:
        bot2.reply_to(message, f"Failed to download. Error: {str(e)}")
        logging.error(f"Download failed: {e}")

# Function to handle incoming messages with URL and optional start and end times
@bot2.message_handler(func=lambda message: True)
def handle_links(message):
    # Check if the user is a member of the required channel
    if not is_user_in_channel(message.from_user.id):
        bot2.reply_to(message, f"Please join our channel to use this bot: {CHANNEL_ID}")
        return
    text = message.text.split()
    url = text[0]
    # Validate the URL before proceeding
    if not is_valid_url(url):
        bot2.reply_to(message, "The provided URL is not valid. Please enter a valid URL.")
        return
    # Handle Instagram URLs separately
    if "instagram.com" in url:
        try:
            bot2.reply_to(message, "Downloading Instagram image, this may take some time...")
            image_path = download_instagram_image(url)
            with open(image_path, 'rb') as image:
                bot2.send_photo(message.chat.id, image)
            os.remove(image_path)  # Clean up by removing the file after sending
        except Exception as e:
            bot2.reply_to(message, f"Failed to download Instagram image. Error: {str(e)}")
            logging.error(f"Instagram download failed: {e}")
        return

    # Extract optional start and end times
    start_time = text[1] if len(text) > 1 else None
    end_time = text[2] if len(text) > 2 else None
    # Start download in a new thread
    threading.Thread(target=download_and_send, args=(message, url, start_time, end_time)).start()

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