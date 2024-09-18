import os
import logging
import threading
from flask import Flask, request
import telebot
import yt_dlp
import requests
from concurrent.futures import ThreadPoolExecutor

# Load the API token and channel ID from environment variables
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

# Function to sanitize file names
def sanitize_filename(filename, max_length=200):
    import re
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)
    return filename.strip()[:max_length]

# Function to check the user status in the channel
def check_user_status(user_id):
    try:
        member = bot2.get_chat_member(CHANNEL_ID, user_id)
        if member.status in ['administrator', 'creator']:
            return 'admin'
        elif member.status == 'member':
            return 'member'
        elif member.status == 'kicked':
            return 'banned'
        else:
            return 'not_member'
    except Exception as e:
        logging.error(f"Error checking user status: {e}")
        return 'error'

# Function to download media using yt-dlp
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

# Function to download and send media asynchronously
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

# Bot command to start and welcome the user
@bot2.message_handler(commands=['start'])
def send_welcome(message):
    bot2.reply_to(message, f"Welcome! Please join our channel: {CHANNEL_ID} before using the bot.")
    bot2.reply_to(message, "After joining, you can paste the link of the content you want to download.")

# Handle media links and verify user status
@bot2.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.from_user.id
    status = check_user_status(user_id)

    if status == 'admin':
        bot2.reply_to(message, "Hello admin! You have full access to the bot.")
        url = message.text
        threading.Thread(target=download_and_send, args=(message, url)).start()

    elif status == 'member':
        bot2.reply_to(message, "Hello member! You can now use the bot.")
        url = message.text
        threading.Thread(target=download_and_send, args=(message, url)).start()

    elif status == 'banned':
        bot2.reply_to(message, "You are banned from the channel. You cannot use this bot.")

    elif status == 'not_member':
        bot2.reply_to(message, f"Please join our channel first: {CHANNEL_ID}")
        join_button = telebot.types.InlineKeyboardMarkup()
        join_button.add(telebot.types.InlineKeyboardButton('Join Channel', url=f"https://t.me/{CHANNEL_ID[1:]}"))
        bot2.send_message(message.chat.id, "After joining, try again.", reply_markup=join_button)

    else:
        bot2.reply_to(message, "There was an error checking your status. Please try again later.")

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
