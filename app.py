import os
import logging
import threading
from flask import Flask, request
import telebot
import yt_dlp
import requests
from concurrent.futures import ThreadPoolExecutor

# Load API tokens and channel IDs from environment variables
API_TOKEN_2 = os.getenv('API_TOKEN_2')
CHANNEL_ID = os.getenv('CHANNEL_ID')  # Your Channel ID with @ like '@YourChannel'

# Instagram credentials from environment variables
INSTAGRAM_APP_ID = os.getenv('INSTAGRAM_APP_ID')
INSTAGRAM_APP_SECRET = os.getenv('INSTAGRAM_APP_SECRET')
INSTAGRAM_ACCESS_TOKEN = os.getenv('INSTAGRAM_ACCESS_TOKEN')

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

# Function to check the user status in the channel
def check_user_status(user_id):
    try:
        member = bot2.get_chat_member(CHANNEL_ID, user_id)
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

# Function to sanitize filenames
def sanitize_filename(filename, max_length=200):
    import re
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)
    return filename.strip()[:max_length]

# Function to extract Instagram media ID from URL
def extract_instagram_media_id(url):
    import re
    match = re.search(r'instagram\.com/[^/]+/([^/?#&]+)', url)
    if match:
        return match.group(1)
    else:
        raise Exception("Invalid Instagram URL")

# Function to fetch media URL from Instagram Graph API
# Function to fetch media URL from Instagram Graph API
def get_instagram_media_url(media_id):
    url = f"https://graph.instagram.com/{media_id}?fields=id,media_type,media_url,thumbnail_url&access_token={INSTAGRAM_ACCESS_TOKEN}"
    
    response = requests.get(url)
    
    if response.status_code == 200:
        data = response.json()
        if 'media_url' in data:
            media_url = data['media_url']
            logging.info(f"Instagram media URL fetched: {media_url}")
            return media_url
        else:
            logging.error(f"No media URL found in response: {data}")
            raise Exception("No media URL found in Instagram response.")
    else:
        logging.error(f"Instagram API error: {response.status_code} {response.text}")
        raise Exception(f"Failed to get media from Instagram: {response.status_code} {response.text}")

# Function to download Instagram media
def download_instagram_media(url):
    logging.info(f"Downloading Instagram media from URL: {url}")
    media_id = extract_instagram_media_id(url)
    media_url = get_instagram_media_url(media_id)
    
    # Download the actual media
    response = requests.get(media_url, stream=True)
    file_name = f"{output_dir}{sanitize_filename(media_id)}.jpg"  # Adjust extension as needed
    with open(file_name, 'wb') as f:
        for chunk in response.iter_content(chunk_size=1024):
            if chunk:
                f.write(chunk)
    return file_name

# Function to download media based on platform
def download_media(url):
    logging.info(f"Attempting to download media from URL: {url}")

    if 'instagram.com' in url:
        logging.info("Processing Instagram URL")
        return download_instagram_media(url)

    elif 'twitter.com' in url or 'x.com' in url or 'threads.com' in url:
        logging.info("Processing Twitter/Threads/X URL")
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
        logging.info("Processing YouTube URL")
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
        logging.info("Processing Facebook URL")
        ydl_opts = {
            'format': 'best',
            'outtmpl': f'{output_dir}%(title)s.%(ext)s',
            'socket_timeout': 15,
        }

    else:
        logging.error(f"Unsupported URL: {url}")
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

# Function to run tasks after admin verification
def run_task(message):
    try:
        url = message.text
        user_id = message.from_user.id
        status = check_user_status(user_id)

        if status == 'admin':
            bot2.reply_to(message, "Admin verification successful. Starting download...")
            download_and_send(message, url)
        elif status == 'member':
            bot2.reply_to(message, "Hello Member! You cannot start this task. Please contact an admin.")
        elif status == 'banned':
            bot2.reply_to(message, "You are banned from the channel.")
        elif status == 'not_member':
            bot2.reply_to(message, f"Please join the channel first: {CHANNEL_ID}")
        else:
            bot2.reply_to(message, "There was an error checking your status. Please try again later.")
    except Exception as e:
        bot2.reply_to(message, f"Failed to run task. Error: {str(e)}")
        logging.error(f"Task execution failed: {e}")

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
    # Start a new thread for the task to avoid blocking the bot
    threading.Thread(target=run_task, args=(message,)).start()

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
