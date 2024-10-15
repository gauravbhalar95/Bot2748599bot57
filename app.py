import os
import logging
import threading
from flask import Flask, request
import telebot
import yt_dlp
from concurrent.futures import ThreadPoolExecutor

# Load API tokens and channel IDs from environment variables
API_TOKEN_2 = os.getenv('API_TOKEN_2')
CHANNEL_ID = os.getenv('CHANNEL_ID')  # Your Channel ID with @ like '@YourChannel'

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

# Function to sanitize filenames
def sanitize_filename(filename, max_length=200):
    import re
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)  # Remove invalid characters
    return filename.strip()[:max_length]

# yt-dlp options optimized for speed
def get_ydl_opts():
    return {
        'format': 'bestvideo+bestaudio/best',  # Best quality
        'outtmpl': f'{output_dir}%(title)s.%(ext)s',  # Save path for media files
        'cookiefile': cookies_file,  # Use cookie file if required for authentication
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }],
        'socket_timeout': 10,  # Reduced timeout to fail faster on poor connections
        'retries': 3,  # Retry on failure
        'quiet': True,  # Suppress verbose output to boost speed
        'concurrent_fragment_downloads': 5,  # Maximize concurrency for fragment downloads
        'noprogress': True,  # Disable progress bar for faster threading
    }

# Function to download media using optimized yt-dlp
def download_media(url, username=None, password=None):
    logging.debug(f"Attempting to download media from URL: {url}")

    # Instagram login, if credentials are provided
    ydl_opts = get_ydl_opts()
    if username and password:
        ydl_opts['username'] = username
        ydl_opts['password'] = password

    # Log URL type
    if 'instagram.com' in url:
        logging.debug("Processing Instagram URL")
    elif 'twitter.com' in url or 'x.com' in url:
        logging.debug("Processing Twitter/X URL")
    elif 'youtube.com' in url or 'youtu.be' in url:
        logging.debug("Processing YouTube URL")
    elif 'facebook.com' in url:
        logging.debug("Processing Facebook URL")
    else:
        logging.error(f"Unsupported URL: {url}")
        raise Exception("Unsupported URL!")

    try:
        # Download media with yt-dlp
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info_dict)

        # Check and handle partial downloads
        part_file_path = f"{file_path}.part"
        if os.path.exists(part_file_path):
            os.rename(part_file_path, file_path)
            logging.debug(f"Renamed partial file: {part_file_path} to {file_path}")

        if os.path.exists(file_path):
            logging.debug(f"Downloaded file found: {file_path}")
            return file_path
        else:
            raise Exception("Download failed: File not found after download.")

    except Exception as e:
        logging.error(f"yt-dlp download error: {str(e)}")
        raise

# Function to handle media download and send asynchronously
def download_and_send(message, url, username=None, password=None):
    try:
        bot2.reply_to(message, "Downloading media, this may take some time...")

        with ThreadPoolExecutor(max_workers=5) as executor:  # Increased workers for parallelism
            future = executor.submit(download_media, url, username, password)
            file_path = future.result()

            # Send the file to the user
            if file_path.lower().endswith('.mp4'):
                with open(file_path, 'rb') as media:
                    bot2.send_video(message.chat.id, media)
            else:
                with open(file_path, 'rb') as media:
                    if file_path.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                        bot2.send_photo(message.chat.id, media)
                    else:
                        bot2.send_document(message.chat.id, media)

            # Clean up by removing the file after sending
            os.remove(file_path)
            logging.debug(f"Deleted file: {file_path}")

    except Exception as e:
        bot2.reply_to(message, f"Failed to download. Error: {str(e)}")
        logging.error(f"Download failed: {e}")

# Function to handle incoming messages
@bot2.message_handler(func=lambda message: True)
def handle_links(message):
    url = message.text

    # Extract Instagram credentials if provided in the message
    username = None
    password = None
    if "@" in url:  # Example: url containing "username:password"
        username, password = url.split('@', 1)  # Assuming format: username:password@url
        url = password  # Change url to actual URL

    # Start a new thread for the task to avoid blocking the bot
    threading.Thread(target=download_and_send, args=(message, url, username, password)).start()

# Flask app setup
app = Flask(__name__)

# Flask routes for webhook handling
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
    # Run the Flask app in debug mode
    app.run(host='0.0.0.0', port=8080, debug=True)