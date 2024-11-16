import os
import logging
import threading
from flask import Flask, request
import telebot
import yt_dlp
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
from telebot import types

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

# Function to fetch available formats
def get_available_formats(url):
    try:
        ydl_opts = {
            'format': 'bestaudio/best',  # Select best quality
            'noplaylist': True,
            'quiet': True
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            formats = info_dict.get('formats', [])
            return formats
    except Exception as e:
        logging.error(f"Error fetching available formats: {str(e)}")
        return []

# Function to create inline buttons for quality selection
def create_quality_buttons(formats):
    buttons = []
    selected_qualities = ['480p', '720p', '1080p', '2160p']  # Target resolutions

    # Filter formats for the specified resolutions
    for f in formats:
        format_note = f.get('format_note', f.get('format'))
        if any(q in format_note for q in selected_qualities):  # Match target resolutions
            buttons.append(types.InlineKeyboardButton(format_note, callback_data=format_note))

    if not buttons:  # If no matches found, create buttons for all available formats
        for f in formats:
            format_note = f.get('format_note', f.get('format'))
            buttons.append(types.InlineKeyboardButton(format_note, callback_data=format_note))

    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(*buttons)
    return keyboard

# Function to download media with selected format
def download_media(url, format_code):
    logging.debug(f"Downloading media from URL: {url} with format: {format_code}")

    ydl_opts = {
        'format': format_code,
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

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info_dict)

        if not os.path.exists(file_path):
            part_file_path = f"{file_path}.part"
            if os.path.exists(part_file_path):
                os.rename(part_file_path, file_path)
            else:
                logging.error(f"Downloaded file not found at path: {file_path}")
                raise Exception("Download failed: File not found after download.")

        return file_path
    except Exception as e:
        logging.error(f"yt-dlp download error: {str(e)}")
        raise

# Function to download and send the media asynchronously
def download_and_send(message, url, format_code):
    if not is_valid_url(url):
        bot2.reply_to(message, "The provided URL is not valid. Please enter a valid URL.")
        return

    try:
        bot2.reply_to(message, "Downloading media, this may take some time...")
        logging.debug("Initiating media download")

        with ThreadPoolExecutor(max_workers=3) as executor:
            future = executor.submit(download_media, url, format_code)
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

# Function to handle links and send quality options
@bot2.message_handler(func=lambda message: True)
def handle_links(message):
    url = message.text

    if not is_valid_url(url):
        bot2.reply_to(message, "The provided URL is not valid. Please enter a valid URL.")
        return

    # Fetch available formats for the video
    formats = get_available_formats(url)
    if formats:
        bot2.reply_to(message, "Please select the video quality:", reply_markup=create_quality_buttons(formats))
    else:
        bot2.reply_to(message, "No available formats found.")

# Function to handle inline button callback for quality selection
@bot2.callback_query_handler(func=lambda call: True)
def handle_quality_selection(call):
    quality = call.data
    url = call.message.text.split('\n')[0]  # Extract URL from the message
    formats = get_available_formats(url)
    
    # Find the format corresponding to the selected quality
    selected_format = next((f for f in formats if f.get('format_note', f.get('format')) == quality), None)
    
    if not selected_format:
        # If the selected quality is not found, try to select one of the common resolutions
        selected_format = next(
            (f for f in formats if any(q in f.get('format_note', f.get('format')) for q in ['480p', '720p', '1080p', '2160p'])),
            None
        )

    if selected_format:
        bot2.answer_callback_query(call.id, text="Starting download...")
        # Call download function with the selected format
        download_and_send(call.message, url, selected_format['format'])
    else:
        bot2.answer_callback_query(call.id, text="Error: Suitable format not found.")

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