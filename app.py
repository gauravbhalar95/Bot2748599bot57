import os
import logging
import threading
from flask import Flask, request
import telebot
import yt_dlp
import requests
from concurrent.futures import ThreadPoolExecutor

# Load the API token from environment variables
API_TOKEN_2 = os.getenv('API_TOKEN_2')
CHANNEL_ID = os.getenv('CHANNEL_ID')  # Channel username with @, like '@YourChannel'

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

# Check if the user has joined the channel automatically
def is_user_in_channel(user_id):
    try:
        # Check if the user is in the channel
        member = bot2.get_chat_member(CHANNEL_ID, user_id)
        # If the user is not banned or kicked, they have joined the channel
        if member.status in ['member', 'administrator', 'creator']:
            return True
    except Exception as e:
        logging.error(f"Error checking channel membership: {e}")
    return False

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
    if 'instagram.com' in url:
        ydl_opts = {
            'format': 'best',
            'outtmpl': f'{output_dir}%(title)s.%(ext)s',
            'cookiefile': cookies_file,
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
            'socket_timeout': 15,
        }
        if '/stories/' in url:
            ydl_opts['format'] = 'bestvideo+bestaudio/best'
            ydl_opts['outtmpl'] = f'{output_dir}%(uploader)s_story.%(ext)s'
        elif '/p/' in url or '/tv/' in url:
            ydl_opts['format'] = 'best'
            ydl_opts['outtmpl'] = f'{output_dir}%(title)s.%(ext)s'

    elif 'threads.com' in url or 'twitter.com' in url or 'x.com' in url:
        ydl_opts = {
            'format': 'best',
            'outtmpl': f'{output_dir}%(title)s.%(ext)s',
            'cookiefile': cookies_file,
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
            'socket_timeout': 15,
        }

    elif 'youtube.com' in url or 'youtu.be' in url:
        ydl_opts = {
            'format': 'best',
            'outtmpl': f'{output_dir}%(title)s.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
            'socket_timeout': 15,
            'cookiefile': cookies_file,
        }

    elif 'facebook.com' in url:
        ydl_opts = {
            'format': 'best',
            'outtmpl': f'{output_dir}%(title)s.%(ext)s',
            'socket_timeout': 15,
        }

    else:
        raise Exception("Unsupported URL!")

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info_dict)
        return file_path
    except Exception as e:
        logging.error(f"yt-dlp download error: {str(e)}")
        raise

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

# Flask app setup
app = Flask(__name__)

# Bot 2 commands and handlers
@bot2.message_handler(commands=['start'])
def send_welcome_bot2(message):
    bot2.reply_to(message, f"Welcome! Please join our channel: {CHANNEL_ID} before using the bot.")
    bot2.reply_to(message, "After joining, you can paste the link of the content you want to download.")

# Handle media links
@bot2.message_handler(func=lambda message: True)
def handle_links(message):
    user_id = message.from_user.id

    # Check if the user has joined the channel
    if is_user_in_channel(user_id):
        url = message.text
        # Start a new thread for the download to avoid blocking the bot
        threading.Thread(target=download_and_send, args=(message, url)).start()
    else:
        # Automatically prompt to join the channel and retry after a short delay
        bot2.reply_to(message, f"Please join our channel first: {CHANNEL_ID}")
        join_button = telebot.types.InlineKeyboardMarkup()
        join_button.add(telebot.types.InlineKeyboardButton('Join Channel', url=f"https://t.me/{CHANNEL_ID[1:]}"))
        bot2.send_message(message.chat.id, "After joining, try again.", reply_markup=join_button)

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
