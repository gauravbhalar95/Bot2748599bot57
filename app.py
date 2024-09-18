import os
import logging
from flask import Flask, request
import telebot
import yt_dlp
import requests

# Load the API token and channel ID from environment variables
API_TOKEN = os.getenv('API_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')  # Your Channel ID with @ like '@YourChannel'

# Initialize the bot
bot = telebot.TeleBot(API_TOKEN)

# Directory to save downloaded files
output_dir = 'downloads/'
cookies_file = 'cookies.txt'

# Create the downloads directory if it does not exist
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# Logging setup
logging.basicConfig(level=logging.INFO)

# Function to check the user status in the channel
def check_user_status(user_id):
    try:
        member = bot.get_chat_member(CHANNEL_ID, user_id)
        logging.info(f"User status: {member.status}")
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

# Task to run after admin verification
def run_task(message):
    try:
        url = message.text
        file_path = download_media(url)
        bot.reply_to(message, "Task completed successfully.")
        
        # Send the media file
        with open(file_path, 'rb') as media:
            if file_path.lower().endswith(('.mp4', '.mkv', '.webm')):
                bot.send_video(message.chat.id, media)
            elif file_path.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                bot.send_photo(message.chat.id, media)
            else:
                bot.send_document(message.chat.id, media)
        
        # Remove the file after sending
        os.remove(file_path)
    except Exception as e:
        bot.reply_to(message, f"Failed to run task. Error: {str(e)}")
        logging.error(f"Task execution failed: {e}")

# Function to sanitize filenames
def sanitize_filename(filename, max_length=200):
    import re
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)
    return filename.strip()[:max_length]

# Function to download media
def download_media(url):
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

    if 'instagram.com' in url:
        if '/stories/' in url:
            ydl_opts['format'] = 'bestvideo+bestaudio/best'
            ydl_opts['outtmpl'] = f'{output_dir}%(uploader)s_story.%(ext)s'
        else:
            ydl_opts['format'] = 'best'
            ydl_opts['outtmpl'] = f'{output_dir}%(title)s.%(ext)s'
    elif 'threads.com' in url or 'twitter.com' in url or 'x.com' in url:
        ydl_opts['format'] = 'best'
        ydl_opts['outtmpl'] = f'{output_dir}%(title)s.%(ext)s'
    elif 'youtube.com' in url or 'youtu.be' in url:
        ydl_opts['format'] = 'best'
        ydl_opts['outtmpl'] = f'{output_dir}%(title)s.%(ext)s'
    elif 'facebook.com' in url:
        ydl_opts['format'] = 'best'
        ydl_opts['outtmpl'] = f'{output_dir}%(title)s.%(ext)s'
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

# Flask app setup
app = Flask(__name__)

# Bot command to start and welcome the user
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    status = check_user_status(user_id)

    if status == 'admin':
        bot.reply_to(message, "Welcome Admin! Your tasks will run automatically.")
        run_task(message)
    elif status == 'member':
        bot.reply_to(message, "Hello Member! Join our tasks or ask the admin to assign them.")
    elif status == 'banned':
        bot.reply_to(message, "You are banned from the channel.")
    elif status == 'not_member':
        bot.reply_to(message, f"Please join the channel first: {CHANNEL_ID}")
    else:
        bot.reply_to(message, "There was an error checking your status. Please try again later.")

# Flask routes for webhook handling
@app.route('/' + API_TOKEN, methods=['POST'])
def getMessage():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "!", 200

@app.route('/')
def webhook():
    bot.remove_webhook()
    bot.set_webhook(url=f'https://bot2-mb9e.onrender.com/{API_TOKEN}', timeout=60)
    return "Webhook set", 200

if __name__ == "__main__":
    # Run the Flask app
    app.run(host='0.0.0.0', port=80)
