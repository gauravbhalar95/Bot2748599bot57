import os
import logging
import threading
from flask import Flask, request
import telebot
import yt_dlp
import instaloader
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

# Instagram credentials for login
INSTAGRAM_USERNAME = os.getenv('username')
INSTAGRAM_PASSWORD = os.getenv('password')

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

# Function to fetch available formats for YouTube videos
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

# Function to download media from YouTube with selected format
def download_youtube_media(url, format_code):
    logging.debug(f"Downloading YouTube media from URL: {url} with format: {format_code}")

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

# Function to download Instagram media using instaloader
def download_instagram_media(url):
    logging.debug(f"Downloading Instagram media from URL: {url}")

    L = instaloader.Instaloader()
    L.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)  # Login using Instagram credentials
    post = instaloader.Post.from_url(L.context, url)

    # Download the post (photo/video)
    L.download_post(post, target=output_dir)

    # Return the file path of the downloaded media
    return os.path.join(output_dir, post.filename)

# Function to create inline buttons for quality selection
def create_quality_buttons(formats):
    buttons = []
    selected_qualities = ['480p', '720p', '1080p', '2160p']  # Target resolutions

    # Filter formats for the specified resolutions
    for f in formats:
        format_note = f.get('format_note', f.get('format'))
        # Check if the format contains any of the target resolutions
        if any(q in format_note for q in selected_qualities):  # Match target resolutions
            buttons.append(types.InlineKeyboardButton(format_note, callback_data=format_note))

    if not buttons:  # If no matches found, create buttons for all available formats
        for f in formats:
            format_note = f.get('format_note', f.get('format'))
            buttons.append(types.InlineKeyboardButton(format_note, callback_data=format_note))

    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(*buttons)
    return keyboard

# Function to download and send the media asynchronously
def download_and_send(message, url, format_code, platform):
    try:
        bot2.reply_to(message, "Downloading media, this may take some time...")
        logging.debug("Initiating media download")

        if platform == "youtube":
            with ThreadPoolExecutor(max_workers=3) as executor:
                future = executor.submit(download_youtube_media, url, format_code)
                file_path = future.result()
        elif platform == "instagram":
            file_path = download_instagram_media(url)

        logging.debug(f"Download completed, file path: {file_path}")

        # Send the downloaded media
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

    # Determine if the URL is from YouTube or Instagram
    if "youtube.com" in url or "youtu.be" in url:
        platform = "youtube"
        formats = get_available_formats(url)

        if not formats:
            bot2.reply_to(message, "No video formats available for this URL.")
            return

        # Create the inline keyboard for video quality selection
        keyboard = create_quality_buttons(formats)

        # Ask user to choose the quality
        bot2.reply_to(message, "Choose the video quality:", reply_markup=keyboard)
    elif "instagram.com" in url:
        platform = "instagram"
        # Directly proceed to download Instagram media
        download_and_send(message, url, None, platform)
    else:
        bot2.reply_to(message, "Unsupported URL. Please provide a YouTube or Instagram link.")
        return

# Function to handle user's quality selection for YouTube
@bot2.callback_query_handler(func=lambda call: True)
def handle_quality_selection(call):
    format_code = call.data
    url = call.message.text.split("\n")[-1]  # Extract URL from the message text

    try:
        # Download and send media
        download_and_send(call.message, url, format_code, "youtube")
    except Exception as e:
        bot2.reply_to(call.message, f"An error occurred while downloading: {str(e)}")
        logging.error(f"Error during download: {str(e)}")

# Start the bot
if __name__ == '__main__':
    # Set up Flask app to expose bot
    app = Flask(__name__)

    @app.route(f'/{API_TOKEN_2}', methods=['POST'])
    def webhook():
        json_str = request.get_data().decode('UTF-8')
        update = telebot.types.Update.de_json(json_str)
        bot2.process_new_updates([update])
        return '!', 200

    app.run(debug=True, port=8080)