import os
import logging
import threading
from flask import Flask, request
import telebot
import yt_dlp
import re  # For regex to detect URLs from multiple platforms

# Load API tokens and channel IDs from environment variables
API_TOKEN_2 = os.getenv('API_TOKEN_2')
CHANNEL_ID = os.getenv('CHANNEL_ID')  # Your Channel ID with @ like '@YourChannel'

# Initialize the bot with debug mode enabled
bot2 = telebot.TeleBot(API_TOKEN_2, parse_mode='HTML')
telebot.logger.setLevel(logging.DEBUG)

# Directory to save downloaded files
output_dir = 'downloads/'
cookies_file = 'cookies.txt'  # Your cookies file

# Ensure the downloads directory exists
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

# Ensure yt-dlp is updated
os.system('yt-dlp -U')

# List to store download history
download_history = []

# Function to sanitize filenames
def sanitize_filename(filename, max_length=200):
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)
    return filename.strip()[:max_length]

# Progress hook to track download progress
def progress_hook(d):
    if d['status'] == 'downloading':
        percent = d.get('_percent_str', '0%').strip()
        eta = d.get('eta', 'N/A')
        speed = d.get('_speed_str', '0 KB/s').strip()
        logging.info(f"Downloading: {percent} complete at {speed}, ETA: {eta}s")
        bot2.send_message(CHANNEL_ID, f"Downloading: {percent} complete at {speed}, ETA: {eta}s")

# Function to download media from any social media platform
def download_media(url):
    logging.debug(f"Attempting to download media from URL: {url}")

    # Setup yt-dlp options with cookies and FFmpeg binary location
    ydl_opts = {
        'format': 'best[ext=mp4]/best',  # Try mp4 format first
        'outtmpl': f'{output_dir}%(title)s.%(ext)s',  # Save path for media files
        'cookiefile': cookies_file,  # Use cookie file if required for authentication
        'socket_timeout': 10,
        'retries': 5,
        'max_filesize': 2 * 1024 * 1024 * 1024,  # Max size 2GB
        'quiet': True,  # Suppress unnecessary output
        'progress_hooks': [progress_hook],  # Add progress hook here
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
        }],
        'ffmpeg_location': '/bin/FFmpeg',  # Update this to your FFmpeg binary path
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)

            # Log the extracted info_dict to debug
            logging.debug(f"Extracted info_dict: {info_dict}")

            if 'title' in info_dict and info_dict['title'] is not None:
                file_path = ydl.prepare_filename(info_dict)
                return file_path
            else:
                logging.error("No title found in the extracted info_dict.")
                raise Exception("Failed to download media: No title found.")

    except Exception as e:
        logging.error(f"yt-dlp download error: {str(e)}")
        raise

# Function to track downloads in history
def track_download(file_path):
    if file_path:
        download_history.append(file_path)

# Function to detect URLs from multiple platforms
def detect_social_media_url(text):
    # Regex for multiple platforms: Instagram, Twitter, Facebook, YouTube
    social_media_regex = (
        r'(https?://(www\.)?instagram\.com/[^\s]+|'  # Instagram
        r'https?://(www\.)?twitter\.com/[^\s]+|'     # Twitter
        r'https?://(www\.)?facebook\.com/[^\s]+|'    # Facebook
        r'https?://(www\.)?youtube\.com/[^\s]+|'     # YouTube
        r'https?://youtu\.be/[^\s]+)'                # YouTube shortened
    )
    match = re.search(social_media_regex, text)
    if match:
        return match.group(0)
    return None

# Function to download and send media (images/videos)
def download_and_send_media(message, url):
    try:
        bot2.reply_to(message, "Downloading media...")
        file_path = download_media(url)

        # Track download in history
        track_download(file_path)

        # Send the media file (image/video)
        with open(file_path, 'rb') as media:
            bot2.send_document(message.chat.id, media)

        # Clean up
        os.remove(file_path)

    except Exception as e:
        bot2.reply_to(message, f"Failed to download media. Error: {e}")

# Command to show download history
@bot2.message_handler(commands=['history'])
def handle_history(message):
    if not download_history:
        bot2.reply_to(message, "No downloads have been made yet.")
    else:
        history_text = "\n".join([f"{i+1}. {os.path.basename(file)}" for i, file in enumerate(download_history)])
        bot2.reply_to(message, f"Download history:\n{history_text}")

# Command to show help information
@bot2.message_handler(commands=['help'])
def handle_help(message):
    help_text = """
    <b>Welcome to the Media Downloader Bot!</b>
    
    Here are the commands you can use:
    - /supported: List supported platforms.
    - /history: Show recent download history.
    
    Just send a URL from Instagram, YouTube, Twitter, or Facebook, and I'll download the media for you!
    """
    bot2.reply_to(message, help_text)

# Handler for any incoming messages
@bot2.message_handler(func=lambda message: True)
def handle_message(message):
    # Check if the message contains a social media URL
    social_media_url = detect_social_media_url(message.text)
    if social_media_url:
        threading.Thread(target=download_and_send_media, args=(message, social_media_url)).start()

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