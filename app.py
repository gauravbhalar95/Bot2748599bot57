import os
import logging
from flask import Flask, request
import telebot
import yt_dlp
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

# Load API tokens and environment variables
API_TOKEN_2 = os.getenv('API_TOKEN_2')
KOYEB_URL = os.getenv('KOYEB_URL')

# Ensure API token is provided
if not API_TOKEN_2:
    raise ValueError("API_TOKEN_2 environment variable not set.")

# Initialize the bot
bot2 = telebot.TeleBot(API_TOKEN_2, parse_mode='HTML')
telebot.logger.setLevel(logging.DEBUG)

# Directory to save downloaded files
output_dir = 'downloads/'
cookies_file = 'cookies.txt'

# Ensure the downloads directory exists
os.makedirs(output_dir, exist_ok=True)

# Enable debug logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Ensure yt-dlp is updated
os.system('yt-dlp -U')

# Rate limiting (simple in-memory limit)
user_download_limits = {}  # Track download requests per user
RATE_LIMIT = 5  # Max downloads per user per hour

def is_valid_url(url):
    """Validate the given URL."""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

def download_media(url):
    """Download media using yt-dlp."""
    logging.debug(f"Downloading media from URL: {url}")
    output_template = f'{output_dir}%(title)s.%(ext)s'

    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'outtmpl': output_template,
        'cookiefile': cookies_file,
        'socket_timeout': 10,
        'retries': 5,
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info_dict)
            if not os.path.exists(file_path):
                raise FileNotFoundError("Download failed: File not found.")
        return file_path
    except Exception as e:
        logging.error(f"yt-dlp download error: {str(e)}")
        raise

def download_and_send(message, url):
    """Download media and send it via Telegram."""
    if not is_valid_url(url):
        bot2.reply_to(message, "The provided URL is not valid.")
        return

    if user_download_limits.get(message.chat.id, 0) >= RATE_LIMIT:
        bot2.reply_to(message, "You have reached the download limit. Please try again later.")
        return

    try:
        bot2.reply_to(message, "Downloading media...")
        logging.debug(f"Initiating media download for user {message.chat.id}")

        with ThreadPoolExecutor(max_workers=3) as executor:
            future = executor.submit(download_media, url)
            file_path = future.result()

            logging.debug(f"Download completed, file path: {file_path}")

            with open(file_path, 'rb') as media:
                if file_path.lower().endswith('.mp4'):
                    bot2.send_video(message.chat.id, media)
                elif file_path.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                    bot2.send_photo(message.chat.id, media)
                else:
                    bot2.send_document(message.chat.id, media)

            os.remove(file_path)
            bot2.reply_to(message, "Download completed successfully.")
            user_download_limits[message.chat.id] = user_download_limits.get(message.chat.id, 0) + 1

    except Exception as e:
        bot2.reply_to(message, f"Failed to download. Error: {str(e)}")
        logging.error(f"Download failed: {e}")

# Flask app setup
app = Flask(__name__)

@app.route('/' + API_TOKEN_2, methods=['POST'])
def getMessage_bot2():
    """Process incoming Telegram webhook updates."""
    try:
        json_str = request.stream.read().decode("utf-8")
        update = telebot.types.Update.de_json(json_str)
        logging.debug(f"Received update: {json_str}")
        bot2.process_new_updates([update])
    except Exception as e:
        logging.error(f"Error processing update: {e}")
    return "!", 200

@app.route('/')
def webhook():
    """Set webhook for Telegram bot."""
    try:
        bot2.remove_webhook()
        webhook_url = f"{KOYEB_URL}/{API_TOKEN_2}"
        bot2.set_webhook(url=webhook_url, timeout=60)
        logging.debug(f"Webhook set to {webhook_url}")
        return "Webhook set", 200
    except Exception as e:
        logging.error(f"Error setting webhook: {e}")
        return "Webhook error", 500

if __name__ == "__main__":
    logging.info("Starting Flask server...")
    app.run(host='0.0.0.0', port=8080, debug=True)