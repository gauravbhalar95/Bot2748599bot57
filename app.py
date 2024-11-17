import os
import logging
import threading
from flask import Flask, request
import telebot
import yt_dlp
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

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

# Ensure yt-dlp is updated
os.system('yt-dlp -U')

# Function to sanitize filenames
def sanitize_filename(filename, max_length=250):
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

# Function to download media with a specified format
def download_media(url, quality='best'):
    logging.debug(f"Attempting to download media from URL: {url} with quality: {quality}")

    # Set up options for yt-dlp
    ydl_opts = {
        'format': f'bestvideo[height<={quality}]+bestaudio/best',  # Use specified quality
        'outtmpl': f'{output_dir}{sanitize_filename("%(title)s")}.%(ext)s',  # Use sanitized title
        'cookiefile': cookies_file,  # Use cookie file if required for authentication
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }],
        'socket_timeout': 10,
        'retries': 5,
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.85 Safari/537.36'
    }

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

# Function to send quality selection buttons
def send_quality_options(message, url):
    markup = InlineKeyboardMarkup()
    markup.row_width = 3
    quality_options = ['1080', '720', '480']  # Add more options if needed
    buttons = [InlineKeyboardButton(text=f"{q}p", callback_data=f"quality:{q}:{url}") for q in quality_options]
    markup.add(*buttons)
    bot2.send_message(message.chat.id, "Please select the download quality:", reply_markup=markup)

# Function to handle quality selection callback
@bot2.callback_query_handler(func=lambda call: call.data.startswith('quality'))
def callback_quality_selection(call):
    _, quality, url = call.data.split(':')
    bot2.answer_callback_query(call.id, f"Selected quality: {quality}p")
    bot2.send_message(call.message.chat.id, f"Downloading media in {quality}p quality. This may take some time...")
    threading.Thread(target=download_and_send, args=(call.message, url, None, None, quality)).start()

# Function to download media and send it asynchronously
def download_and_send(message, url, username=None, password=None, quality='best'):
    if not is_valid_url(url):
        bot2.reply_to(message, "The provided URL is not valid. Please enter a valid URL.")
        return

    try:
        bot2.reply_to(message, "Downloading media, this may take some time...")
        logging.debug("Initiating media download")

        with ThreadPoolExecutor(max_workers=3) as executor:
            future = executor.submit(download_media, url, quality)
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

# Function to handle messages
@bot2.message_handler(func=lambda message: True)
def handle_links(message):
    url = message.text
    if is_valid_url(url):
        send_quality_options(message, url)
    else:
        bot2.reply_to(message, "Invalid URL. Please provide a valid URL.")

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
    app.run(host='0.0.0.0', port=8080, debug=True)