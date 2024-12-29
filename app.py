import os
import logging
from flask import Flask, request
import telebot
import yt_dlp
import re
from urllib.parse import urlparse, parse_qs
from mega import Mega  # Mega.nz Python library

# Load environment variables
API_TOKEN_2 = os.getenv('API_TOKEN_2')
CHANNEL_ID = os.getenv('CHANNEL_ID')  # Example: '@YourChannel'
KOYEB_URL = os.getenv('KOYEB_URL')  # Koyeb URL for webhook

# Initialize bot
bot2 = telebot.TeleBot(API_TOKEN_2, parse_mode='HTML')

# Directories
output_dir = 'downloads/'
cookies_file = 'cookies.txt'

# Ensure downloads directory exists
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# Logging configuration
logging.basicConfig(level=logging.DEBUG)

# Supported domains
SUPPORTED_DOMAINS = ['youtube.com', 'youtu.be', 'instagram.com', 'x.com', 'facebook.com', 'instagram:user.com', 'instagram:story.com', 'Popcorntimes.com', 'PopcornTV.com', 'Pornbox.com', 'XXXYMovies.com', 'VuClip.com', 'XHamster.com', 'XNXX.com', 'XVideos.com']

# Mega client
mega_client = None

# Sanitize filenames for downloaded files
def sanitize_filename(filename, max_length=250):
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)
    return filename.strip()[:max_length]

# Check if a URL is valid and supported
def is_valid_url(url):
    try:
        result = urlparse(url)
        return result.scheme in ['http', 'https'] and any(domain in result.netloc for domain in SUPPORTED_DOMAINS)
    except ValueError:
        return False

# Download media using yt-dlp
def download_media(url, start_time=None, end_time=None):
    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'outtmpl': f'{output_dir}{sanitize_filename("%(title)s")}.%(ext)s',
        'cookiefile': cookies_file,
        'postprocessors': [{'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'}],
        'socket_timeout': 10,
        'retries': 5,
    }

    if start_time and end_time:
        ydl_opts['postprocessor_args'] = ['-ss', start_time, '-to', end_time]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info_dict)
        return file_path
    except Exception as e:
        logging.error("yt-dlp download error", exc_info=True)
        raise

# Upload file to Mega.nz
def upload_to_mega(file_path):
    if mega_client is None:
        raise Exception("Mega client is not logged in. Use /meganz <username> <password> to log in.")

    try:
        file = mega_client.upload(file_path)
        public_link = mega_client.get_upload_link(file)
        return public_link
    except Exception as e:
        logging.error("Error uploading to Mega", exc_info=True)
        raise

# Handle download and upload logic
def handle_download_and_upload(message, url, upload_to_mega_flag):
    if not is_valid_url(url):
        bot2.reply_to(message, "Invalid or unsupported URL. Supported platforms: YouTube, Instagram, Twitter, Facebook.")
        return

    try:
        bot2.reply_to(message, "Downloading the video, please wait...")

        # Extract start and end times if provided in the YouTube URL
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        start_time = query_params.get('start', [None])[0]
        end_time = query_params.get('end', [None])[0]

        # Download media
        file_path = download_media(url, start_time, end_time)

        if upload_to_mega_flag:
            # Upload to Mega.nz
            bot2.reply_to(message, "Uploading the video to Mega.nz, please wait...")
            mega_link = upload_to_mega(file_path)
            bot2.reply_to(message, f"Video has been uploaded to Mega.nz: {mega_link}")
        else:
            # Send video directly
            with open(file_path, 'rb') as video:
                bot2.send_video(message.chat.id, video)

        # Cleanup
        os.remove(file_path)
    except Exception as e:
        logging.error("Download or upload failed", exc_info=True)
        bot2.reply_to(message, f"Download or upload failed: {str(e)}")

# Mega login command
@bot2.message_handler(commands=['meganz'])
def handle_mega_login(message):
    try:
        args = message.text.split(maxsplit=2)
        if len(args) < 3:
            bot2.reply_to(message, "Usage: /meganz <username> <password>")
            return

        username = args[1]
        password = args[2]

        global mega_client
        mega_client = Mega().login(username, password)
        bot2.reply_to(message, "Successfully logged in to Mega.nz!")
    except Exception as e:
        bot2.reply_to(message, f"Login failed: {str(e)}")

# Download and upload to Mega.nz
@bot2.message_handler(commands=['mega'])
def handle_mega(message):
    try:
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            bot2.reply_to(message, "Usage: /mega <URL>")
            return

        url = args[1]
        handle_download_and_upload(message, url, upload_to_mega_flag=True)
    except IndexError:
        bot2.reply_to(message, "Please provide a valid URL after the command: /mega <URL>.")

# Add /profile command to fetch Instagram profile and download all posts
@bot2.message_handler(commands=['profile'])
def handle_instagram_profile(message):
    try:
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            bot2.reply_to(message, "Usage: /profile <Instagram Profile URL>")
            return

        profile_url = args[1].strip()

        # Check if the URL is a valid Instagram profile link
        if 'instagram.com' not in profile_url or '/p/' in profile_url:
            bot2.reply_to(message, "Please provide a valid Instagram profile URL (not a post or reel).")
            return

        bot2.reply_to(message, "Fetching posts from the Instagram profile, please wait...")

        # Set yt-dlp options for profile download
        ydl_opts = {
            'format': 'best[ext=mp4]/best',
            'outtmpl': f'{output_dir}{sanitize_filename("%(uploader)s")}/%(title)s.%(ext)s',
            'cookiefile': cookies_file,
            'socket_timeout': 10,
            'retries': 5,
            'quiet': False,
            'extract_flat': False,  # Ensure full download
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(profile_url, download=True)
                bot2.reply_to(message, f"Successfully downloaded all posts from {info_dict['uploader']}'s profile.")
        except Exception as e:
            logging.error("yt-dlp Instagram profile download error", exc_info=True)
            bot2.reply_to(message, f"Failed to download posts: {str(e)}")
    except Exception as e:
        logging.error("Instagram profile handler error", exc_info=True)
        bot2.reply_to(message, f"An error occurred: {str(e)}")

# Direct download without Mega.nz
@bot2.message_handler(func=lambda message: True, content_types=['text'])
def handle_direct_download(message):
    url = message.text.strip()
    if is_valid_url(url):
        handle_download_and_upload(message, url, upload_to_mega_flag=False)
    else:
        bot2.reply_to(message, "Please provide a valid URL to download the video.")

# Flask app for webhook
app = Flask(__name__)

@app.route('/' + API_TOKEN_2, methods=['POST'])
def bot_webhook():
    bot2.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "!", 200

@app.route('/')
def set_webhook():
    bot2.remove_webhook()
    bot2.set_webhook(url=KOYEB_URL + '/' + API_TOKEN_2, timeout=60)
    return "Webhook set", 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080, debug=True)