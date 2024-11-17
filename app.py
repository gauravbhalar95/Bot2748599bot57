import os
import logging
import threading
import telebot
import yt_dlp
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
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

# Function to get available video qualities
def get_available_qualities(url):
    try:
        ydl_opts = {'quiet': True, 'format': 'bestvideo'}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            formats = info_dict.get('formats', [])
            qualities = {int(fmt['height']): fmt for fmt in formats if fmt.get('vcodec') != 'none'}
            return sorted(qualities.keys(), reverse=True)  # Return available resolutions in descending order
    except Exception as e:
        logging.error(f"Failed to get available qualities: {e}")
        return []

# Function to download media at a selected quality
def download_media(url, quality, username=None, password=None):
    logging.debug(f"Attempting to download media from URL: {url} at quality: {quality}p")

    # Set up options for yt-dlp with filename sanitization
    ydl_opts = {
        'format': f'bestvideo[height<={quality}]+bestaudio/best[height<={quality}]',
        'outtmpl': f'{output_dir}{sanitize_filename("%(title)s")}.%(ext)s',
        'cookiefile': cookies_file,
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }],
        'socket_timeout': 10,
        'retries': 5,
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
def download_and_send_telegram(message, url, requested_quality, username=None, password=None):
    try:
        logging.debug("Initiating media download")

        with ThreadPoolExecutor(max_workers=3) as executor:
            future = executor.submit(download_media, url, requested_quality, username, password)
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
    url = message.text.strip()

    if not is_valid_url(url):
        bot2.reply_to(message, "The provided URL is not valid. Please enter a valid URL.")
        return

    available_qualities = get_available_qualities(url)
    if not available_qualities:
        bot2.reply_to(message, "No available video qualities found for this URL.")
        return

    # Create inline buttons for available qualities
    markup = InlineKeyboardMarkup()
    for quality in available_qualities:
        markup.add(InlineKeyboardButton(f"{quality}p", callback_data=f"quality_{quality}_{url}"))

    bot2.reply_to(
        message,
        "Please select a quality for download:",
        reply_markup=markup
    )

# Handle callback query for quality selection
@bot2.callback_query_handler(func=lambda call: call.data.startswith('quality_'))
def handle_quality_selection(call):
    data_parts = call.data.split('_')
    selected_quality = int(data_parts[1])
    url = '_'.join(data_parts[2:])  # Reconstruct the URL

    bot2.answer_callback_query(call.id, f"Selected {selected_quality}p quality. Downloading...")
    download_and_send_telegram(call.message, url, selected_quality)

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

# Run the bot
async def run_bot():
    loop = asyncio.get_event_loop()
    app.run(host='0.0.0.0', port=8080, debug=True)

if __name__ == "__main__":
    asyncio.run(run_bot())