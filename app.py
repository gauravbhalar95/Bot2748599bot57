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

# Ensure yt-dlp is installed and updated
os.system('pip install -U yt-dlp')

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

# Function to get available video formats
def get_video_formats(url):
    with yt_dlp.YoutubeDL() as ydl:
        info_dict = ydl.extract_info(url, download=False)
        formats = info_dict.get('formats', [])
        available_qualities = []
        for f in formats:
            resolution = f.get('height')
            if resolution:
                available_qualities.append(f"{resolution}p")
        return available_qualities

# Function to download media with specified quality
def download_media(url, quality='best', username=None, password=None):
    logging.debug(f"Attempting to download media from URL: {url} with quality: {quality}")

    # Set up options for yt-dlp
    ydl_opts = {
        'format': f'{quality}[ext=mp4]/bestvideo+bestaudio/best',  # Select the specified quality or best
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

# Function to handle inline keyboard callback for quality selection
@bot2.callback_query_handler(func=lambda call: True)
def handle_quality_selection(call):
    quality = call.data
    url = call.message.reply_to_message.text  # Assume the original URL is in a replied message
    bot2.reply_to(call.message, f"Downloading with quality: {quality}. This may take some time...")
    logging.debug(f"Quality selected: {quality} from URL: {url}")
    threading.Thread(target=download_and_send, args=(call.message, url, None, None, quality)).start()

# Function to download media and send it asynchronously
def download_and_send(message, url, username=None, password=None, quality='best'):
    if not is_valid_url(url):
        bot2.reply_to(message, "The provided URL is not valid. Please enter a valid URL.")
        return

    try:
        bot2.reply_to(message, "Downloading media, this may take some time...")
        logging.debug("Initiating media download")

        # Remove ThreadPoolExecutor as we're using threading
        threading.Thread(target=download_and_send_task, args=(message, url, username, password, quality)).start()

    except Exception as e:
        bot2.reply_to(message, f"Failed to download. Error: {str(e)}")
        logging.error(f"Download failed: {e}")

def download_and_send_task(message, url, username, password, quality):
    try:
        file_path = download_media(url, quality, username, password)
        logging.debug(f"Download completed, file path: {file_path}")

        # Handle sending the downloaded file
        with open(file_path, 'rb') as media:
            if file_path.lower().endswith('.mp4'):
                bot2.send_video(message.chat.id, media)
            elif file_path.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                bot2.send_photo(message.chat.id, media)
            else:
                bot2.send_document(message.chat.id, media)

        os.remove(file_path)
        bot2.reply_to(message, "Download and sending completed successfully.")
    except Exception as e:
        bot2.reply_to(message, f"Error during download: {e}")
        logging.error(f"Error during download: {e}")

# Function to handle messages and provide quality selection
@bot2.message_handler(func=lambda message: True)
def handle_links(message):
    url = message.text

    if not is_valid_url(url):
        bot2.reply_to(message, "The provided URL is not valid. Please enter a valid URL.")
        return

    # Get available video qualities
    available_qualities = get_video_formats(url)
    available_qualities = list(set(available_qualities))  # Remove duplicates

    if not available_qualities:
        bot2.reply_to(message, "No available qualities found for this video.")
        return

    # Add 'best' as an option
    available_qualities.insert(0, 'best')

    # Display quality selection inline keyboard
    markup = InlineKeyboardMarkup()
    for quality in available_qualities:
        markup.add(InlineKeyboardButton(text=quality, callback_data=quality))

    bot2.reply_to(message, "Select video quality:", reply_markup=markup)

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