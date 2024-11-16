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
API_TOKEN = os.getenv('API_TOKEN_2')  # Set this in your environment
WEBHOOK_URL = os.getenv('KOYEB_URL')  # Hosting URL
CHANNEL_ID = os.getenv('CHANNEL_ID')  # Channel ID with @ like '@YourChannel'

# Initialize the bot with debug mode enabled
bot = telebot.TeleBot(API_TOKEN, parse_mode='HTML')
telebot.logger.setLevel(logging.DEBUG)

# Directory to save downloaded files
output_dir = 'downloads/'
cookies_file = 'cookies.txt'  # YouTube cookies file

# Ensure the downloads directory exists
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Ensure yt-dlp is updated
os.system('yt-dlp -U')

# Function to sanitize filenames
def sanitize_filename(filename, max_length=250):
    import re
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)
    return filename.strip()[:max_length]

# Validate URLs
def is_valid_url(url):
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

# Identify the platform based on the URL
def identify_platform(url):
    if 'instagram.com' in url:
        return 'instagram'
    elif 'twitter.com' in url:
        return 'twitter'
    elif 'facebook.com' in url:
        return 'facebook'
    elif 'pinterest.com' in url:
        return 'pinterest'
    else:
        return 'unknown'

# Function to download media
def download_media(url, quality='best', username=None, password=None):
    logging.debug(f"Attempting to download media from URL: {url}")

    platform = identify_platform(url)
    ydl_opts = {
        'format': 'best',  # Set default to 'best' quality for all platforms
        'outtmpl': f'{output_dir}{sanitize_filename("%(title)s")}.%(ext)s',
        'retries': 5,
        'socket_timeout': 10,
        'user-agent': 'Mozilla/5.0'
    }

    # Use different options based on the platform
    if platform == 'instagram':
        ydl_opts['extractor_args'] = {'instagram': {'username': username, 'password': password}}
    elif platform == 'twitter':
        ydl_opts['extractor_args'] = {'twitter': {'username': username, 'password': password}}
    elif platform == 'facebook':
        ydl_opts['cookies'] = cookies_file  # Example: use cookies for Facebook if needed
    elif platform == 'pinterest':
        ydl_opts['quiet'] = True  # Example: customize options for Pinterest if required
    else:
        logging.error("Unsupported platform.")
        raise Exception("Unsupported platform. Only Instagram, Twitter, Facebook, and Pinterest URLs are supported.")

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

# Handle quality selection and initiate download
def download_and_send(message, url, quality='best', username=None, password=None):
    try:
        if not is_valid_url(url):
            bot.reply_to(message, "The provided URL is not valid. Please enter a valid URL.")
            return

        bot.reply_to(message, f"Downloading in {quality}p quality. This may take some time...")
        logging.debug("Initiating media download")

        with ThreadPoolExecutor(max_workers=3) as executor:
            file_path = executor.submit(download_media, url, quality, username, password).result()

        logging.debug(f"Download completed, file path: {file_path}")

        if os.path.exists(file_path):
            with open(file_path, 'rb') as media:
                if file_path.lower().endswith('.mp4'):
                    bot.send_video(message.chat.id, media)
                elif file_path.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                    bot.send_photo(message.chat.id, media)
                else:
                    bot.send_document(message.chat.id, media)

            os.remove(file_path)
            bot.reply_to(message, "Download and sending completed successfully.")
        else:
            bot.reply_to(message, "Error: File not found after download.")

    except Exception as e:
        bot.reply_to(message, f"Failed to download. Error: {str(e)}")
        logging.error(f"Download failed: {e}")

# Handle incoming messages
@bot.message_handler(func=lambda message: True)
def handle_links(message):
    url = message.text.strip()

    if not is_valid_url(url):
        bot.reply_to(message, "The provided URL is not valid. Please enter a valid URL.")
        return

    platform = identify_platform(url)
    if platform == 'unknown':
        bot.reply_to(message, "Unsupported platform. Please provide a URL from Instagram, Twitter, Facebook, or Pinterest.")
        return

    markup = InlineKeyboardMarkup()
    for quality in ['480', '720', '1080', '2160']:
        markup.add(InlineKeyboardButton(text=f"{quality}p", callback_data=f"{url}|{quality}|None|None"))

    bot.reply_to(message, "Select the quality for download:", reply_markup=markup)

# Handle inline button presses
@bot.callback_query_handler(func=lambda call: True)
def handle_quality_selection(call):
    try:
        url, quality, username, password = call.data.split('|')
        threading.Thread(target=download_and_send, args=(call.message, url, quality, username, password)).start()
    except Exception as e:
        bot.answer_callback_query(call.id, f"Error: {str(e)}")

# Flask app setup
app = Flask(__name__)

# Flask route to handle webhook updates
@app.route(f'/{API_TOKEN}', methods=['POST'])
def webhook_update():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "!", 200

# Health check route
@app.route('/health')
def health_check():
    return "OK", 200

# Flask app startup
@app.route('/')
def set_webhook():
    bot.remove_webhook()
    success = bot.set_webhook(url=f'{WEBHOOK_URL}/{API_TOKEN}')
    if success:
        return "Webhook set successfully", 200
    return "Failed to set webhook", 500

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080, debug=True)