import os
import logging
import threading
import telebot
import yt_dlp
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
from flask import Flask, request
import asyncio

# Load API tokens and channel IDs from environment variables
API_TOKEN_2 = os.getenv('API_TOKEN_2')
CHANNEL_ID = os.getenv('CHANNEL_ID')  # Your Telegram Channel ID with @ like '@YourChannel'

# Initialize the Telegram bot with debug mode enabled
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

# Ensure yt-dlp is updated
os.system('yt-dlp -U')

def sanitize_filename(filename, max_length=250):  # Reduce max_length if needed
    import re
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)  # Remove invalid characters
    return filename.strip()[:max_length]

# Function to validate URLs
def is_valid_url(url):
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

# Function to extract available video formats and options
def get_available_formats(url):
    try:
        ydl_opts = {
            'quiet': True,
            'force_generic_extractor': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            formats = info_dict.get('formats', [])
            available_qualities = {}

            for fmt in formats:
                if fmt.get('ext') == 'mp4':
                    quality = fmt.get('height')
                    if quality:
                        available_qualities[quality] = fmt.get('url')

            return available_qualities

    except Exception as e:
        logging.error(f"Error extracting video formats: {str(e)}")
        return {}

# Function to download media
def download_media(url, quality, username=None, password=None):
    logging.debug(f"Attempting to download media from URL: {url} at quality: {quality}")

    # Set up options for yt-dlp with filename sanitization
    ydl_opts = {
        'format': f'best[height={quality}]/best',  # Select the best quality of the specified height
        'outtmpl': f'{output_dir}{sanitize_filename("%(title)s")}.%(ext)s',  # Use sanitized title
        'cookiefile': cookies_file,  # Use cookie file if required for authentication
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }],
        'socket_timeout': 10,
        'retries': 5,  # Retry on download errors
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.85 Safari/537.36'
    }

    if username and password:
        ydl_opts['username'] = username
        ydl_opts['password'] = password

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info_dict)

        if not os.path.exists(file_path):
            part_file_path = f"{file_path}.part"
            if os.path.exists(part_file_path):
                os.rename(part_file_path, file_path)
                logging.debug(f"Renamed partial file: {part_file_path} to {file_path}")
            else:
                logging.error(f"Downloaded file not found at path: {file_path}")
                raise Exception("Download failed: File not found after download.")

        return file_path

    except Exception as e:
        logging.error(f"yt-dlp download error: {str(e)}")
        raise

# Function to download media and send it asynchronously to Telegram
def download_and_send_telegram(message, url, quality, username=None, password=None):
    if not is_valid_url(url):
        bot2.reply_to(message, "The provided URL is not valid. Please enter a valid URL.")
        return

    try:
        bot2.reply_to(message, f"Downloading media at {quality}p quality, this may take some time...")
        logging.debug("Initiating media download")

        with ThreadPoolExecutor(max_workers=3) as executor:
            future = executor.submit(download_media, url, quality, username, password)
            file_path = future.result()

            logging.debug(f"Download completed, file path: {file_path}")

            if file_path.lower().endswith('.mp4'):
                with open(file_path, 'rb') as media:
                    bot2.send_video(message.chat.id, media)
            else:
                with open(file_path, 'rb') as media:
                    if file_path.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                        bot2.send_photo(message.chat.id, media)
                    else:
                        bot2.send_document(message.chat.id, media)

            os.remove(file_path)
            bot2.reply_to(message, "Download and sending completed successfully.")

    except Exception as e:
        bot2.reply_to(message, f"Failed to download. Error: {str(e)}")
        logging.error(f"Download failed: {e}")

# Function to handle messages from Telegram
@bot2.message_handler(func=lambda message: True)
def handle_telegram_links(message):
    url = message.text

    # First, get the available formats
    available_qualities = get_available_formats(url)

    if not available_qualities:
        bot2.reply_to(message, "No available video qualities found.")
        return

    # Show quality options to the user
    quality_options = "\n".join([f"{quality}p" for quality in available_qualities.keys()])
    bot2.reply_to(message, f"Available video qualities:\n{quality_options}\n\nPlease choose a quality to download (e.g., 360p, 480p, 720p, etc.).")

    # Store the URL and available qualities for later processing
    bot2.register_next_step_handler(message, process_quality_selection, url, available_qualities)

def process_quality_selection(message, url, available_qualities):
    # Retrieve the quality selected by the user
    selected_quality = message.text.strip()

    # Validate the selected quality
    try:
        quality = int(selected_quality.replace('p', ''))
        if quality not in available_qualities:
            raise ValueError("Invalid quality selected.")
    except ValueError:
        bot2.reply_to(message, "Please select a valid quality from the available options.")
        return

    # Proceed to download and send the video
    username = None
    password = None
    if "@" in url:
        username, password = url.split('@', 1)
        url = password

    threading.Thread(target=download_and_send_telegram, args=(message, url, quality, username, password)).start()

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

# Run the bot
async def run_bot():
    loop = asyncio.get_event_loop()
    app.run(host='0.0.0.0', port=8080, debug=True)

if __name__ == "__main__":
    asyncio.run(run_bot())