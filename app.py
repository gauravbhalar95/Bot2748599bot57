import os
import logging
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import yt_dlp
from flask import Flask, request
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor

# Load API tokens and channel ID from environment variables
API_TOKEN_2 = os.getenv('API_TOKEN_2')  # Telegram bot token
CHANNEL_ID = os.getenv('CHANNEL_ID')  # Telegram channel ID
bot2 = telebot.TeleBot(API_TOKEN_2, parse_mode='HTML')

# Logging setup
logging.basicConfig(level=logging.DEBUG)

# Flask app setup
app = Flask(__name__)

# Output directory and cookie file
output_dir = 'downloads/'
cookies_file = 'cookies.txt'
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

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

# Fetch available video qualities
def get_available_qualities(url):
    try:
        ydl_opts = {'quiet': True, 'format': 'bestvideo'}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            formats = info_dict.get('formats', [])
            qualities = {int(fmt['height']): fmt for fmt in formats if fmt.get('vcodec') != 'none'}
            return sorted(qualities.keys(), reverse=True)  # Return sorted qualities
    except Exception as e:
        logging.error(f"Error fetching qualities: {e}")
        return []

# Download media function
def download_media(url, quality, username=None, password=None):
    logging.debug(f"Downloading media from URL: {url} with quality: {quality}p")
    ydl_opts = {
        'format': f'bestvideo[height<={quality}]+bestaudio/best[height<={quality}]',
        'outtmpl': f'{output_dir}{sanitize_filename("%(title)s")}.%(ext)s',
        'cookiefile': cookies_file,
        'postprocessors': [{'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'}],
        'socket_timeout': 10,
        'retries': 5,
        'user-agent': 'Mozilla/5.0'
    }
    if username and password:
        ydl_opts['username'] = username
        ydl_opts['password'] = password
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info_dict)
        return file_path
    except Exception as e:
        logging.error(f"yt-dlp download error: {str(e)}")
        raise

# Function to download and send media
def download_and_send_telegram(message, url, quality, username=None, password=None):
    try:
        bot2.reply_to(message, "Downloading media, please wait...")
        with ThreadPoolExecutor(max_workers=3) as executor:
            future = executor.submit(download_media, url, quality, username, password)
            file_path = future.result()
        with open(file_path, 'rb') as media:
            if file_path.lower().endswith('.mp4'):
                bot2.send_video(message.chat.id, media)
            else:
                bot2.send_document(message.chat.id, media)
        os.remove(file_path)
        bot2.reply_to(message, "Download and sending completed successfully.")
    except Exception as e:
        bot2.reply_to(message, f"Failed to download. Error: {str(e)}")
        logging.error(f"Download failed: {e}")

# Handle Telegram messages
@bot2.message_handler(func=lambda message: True)
def handle_telegram_links(message):
    url = message.text.strip()
    if not is_valid_url(url):
        bot2.reply_to(message, "Invalid URL. Please enter a valid URL.")
        return
    available_qualities = get_available_qualities(url)
    if not available_qualities:
        bot2.reply_to(message, "No available video qualities found for this URL.")
        return
    markup = InlineKeyboardMarkup()
    for quality in available_qualities:
        callback_data = f"{quality}:{url}"
        markup.add(InlineKeyboardButton(f"{quality}p", callback_data=callback_data))
    bot2.reply_to(message, "Select a quality for download:", reply_markup=markup)

# Handle inline button callback queries
@bot2.callback_query_handler(func=lambda call: True)
def handle_quality_selection(call):
    try:
        data_parts = call.data.split(':')
        selected_quality = int(data_parts[0])
        url = data_parts[1]
        bot2.answer_callback_query(call.id, f"Selected {selected_quality}p. Downloading...")
        download_and_send_telegram(call.message, url, selected_quality)
    except Exception as e:
        bot2.send_message(call.message.chat.id, f"Error handling selection: {str(e)}")
        logging.error(f"Callback data error: {e}")

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

# Run Flask app
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080, debug=True)