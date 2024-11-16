import os
import logging
import threading
from flask import Flask, request
import telebot
import yt_dlp
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# Load API tokens from environment variables
API_TOKEN = os.getenv('API_TOKEN')  # Make sure to set this in your environment
CHANNEL_ID = os.getenv('CHANNEL_ID')  # Optional: Channel ID with '@' like '@YourChannel'

# Initialize the bot
bot = telebot.TeleBot(API_TOKEN, parse_mode='HTML')
telebot.logger.setLevel(logging.DEBUG)

# Directory to save downloaded files
output_dir = 'downloads/'
cookies_file = 'cookies.txt'  # Optional: YouTube cookies file for auth

# Ensure the downloads directory exists
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Ensure yt-dlp is up to date
os.system('yt-dlp -U')

# Flask app setup
app = Flask(__name__)

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

# Function to download media with selected quality
def download_media(url, quality='best', username=None, password=None):
    logging.debug(f"Attempting to download media from URL: {url}")

    ydl_opts = {
        'format': f'bestvideo[height<={quality}]+bestaudio/best[height<={quality}]',  # Quality format
        'outtmpl': f'{output_dir}{sanitize_filename("%(title)s")}.%(ext)s',
        'cookiefile': cookies_file,
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }],
        'retries': 5,
        'socket_timeout': 10,
        'user-agent': 'Mozilla/5.0'
    }

    if username and password:
        ydl_opts['username'] = username
        ydl_opts['password'] = password

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            return ydl.prepare_filename(info_dict)

    except Exception as e:
        logging.error(f"yt-dlp download error: {str(e)}")
        raise

# Handle quality selection and initiate download
def download_and_send(message, url, quality):
    try:
        bot.reply_to(message, f"Downloading in {quality}p quality. This may take some time...")
        with ThreadPoolExecutor(max_workers=3) as executor:
            file_path = executor.submit(download_media, url, quality).result()
        
        if os.path.exists(file_path):
            with open(file_path, 'rb') as media:
                bot.send_video(message.chat.id, media) if file_path.lower().endswith('.mp4') else bot.send_document(message.chat.id, media)
            os.remove(file_path)
            bot.reply_to(message, "Download and sending completed successfully.")
        else:
            bot.reply_to(message, "Error: File not found after download.")

    except Exception as e:
        bot.reply_to(message, f"Failed to download. Error: {str(e)}")

# Handle incoming messages
@bot.message_handler(func=lambda message: True)
def handle_links(message):
    url = message.text.strip()
    if not is_valid_url(url):
        bot.reply_to(message, "The provided URL is not valid. Please enter a valid URL.")
        return

    markup = InlineKeyboardMarkup()
    for quality in ['480', '720', '1080', '2160']:
        markup.add(InlineKeyboardButton(text=f"{quality}p", callback_data=f"{url}|{quality}"))

    bot.reply_to(message, "Select the quality for download:", reply_markup=markup)

# Handle inline button presses
@bot.callback_query_handler(func=lambda call: True)
def handle_quality_selection(call):
    try:
        url, quality = call.data.split('|')
        threading.Thread(target=download_and_send, args=(call.message, url, quality)).start()
    except Exception as e:
        bot.answer_callback_query(call.id, f"Error: {str(e)}")

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
    bot.set_webhook(url=os.getenv('WEBHOOK_URL') + '/' + API_TOKEN)
    return "Webhook set", 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080, debug=True)