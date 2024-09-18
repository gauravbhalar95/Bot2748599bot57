import os
import logging
import threading
from flask import Flask, request
import telebot
from concurrent.futures import ThreadPoolExecutor

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
    bot.reply_to(message, "Task is running automatically, since you're an admin.")
    # Add the task logic you want to run here
    # Example task: Send a notification to the channel or perform any action.
    bot.send_message(message.chat.id, "Performing the admin task now...")
    # You can add other logic here, such as running automation, sending messages, etc.

# Sanitize file names to prevent errors
def sanitize_filename(filename, max_length=200):
    import re
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)
    return filename.strip()[:max_length]

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


# Flask app setup
app = Flask(__name__)

# Bot command to start and welcome the user
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    status = check_user_status(user_id)
    
    if status == 'admin':
        bot.reply_to(message, "Welcome Admin! Your tasks will run automatically.")
        # Start tasks automatically for admins
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
