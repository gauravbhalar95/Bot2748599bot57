import os
import logging
from flask import Flask, request
import telebot
import yt_dlp
from mega import Mega
import re

# Load API tokens and channel IDs from environment variables
API_TOKEN_2 = os.getenv('API_TOKEN_2')
CHANNEL_ID = os.getenv('CHANNEL_ID')  # Your Channel ID like '@YourChannel'

# Initialize the bot
bot2 = telebot.TeleBot(API_TOKEN_2, parse_mode='HTML')

# Directory to save downloaded files
output_dir = 'downloads/'
cookies_file = 'cookies.txt'

# Ensure the downloads directory exists
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# Logging configuration
logging.basicConfig(level=logging.DEBUG)

# Supported domains
SUPPORTED_DOMAINS = ['youtube.com', 'youtu.be', 'instagram.com', 'x.com', 'facebook.com']

# Sanitize filename
def sanitize_filename(filename, max_length=250):
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)  # Remove invalid characters
    return filename.strip()[:max_length]

# Validate URL
def is_valid_url(url):
    try:
        result = urlparse(url)
        return result.scheme in ['http', 'https'] and any(domain in result.netloc for domain in SUPPORTED_DOMAINS)
    except ValueError:
        return False

# Download media
def download_media(url):
    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'outtmpl': f'{output_dir}{sanitize_filename("%(title)s")}.%(ext)s',
        'cookiefile': cookies_file,
        'postprocessors': [{'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'}],
        'socket_timeout': 10,
        'retries': 5,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info_dict)
        return file_path
    except Exception as e:
        logging.error("yt-dlp download error", exc_info=True)
        raise

# Mega.nz login and upload
def mega_login(username, password):
    try:
        mega_client = Mega()
        # Attempt to login to Mega.nz with provided credentials
        mega_session = mega_client.login(username, password)
        logging.info(f"Logged into Mega.nz as {username} successfully.")
        return mega_session
    except Exception as e:
        logging.error(f"Mega.nz login failed for {username}: {str(e)}")
        return None

# Download and upload to Mega
def download_and_upload_to_mega(message, url, username, password):
    if not is_valid_url(url):
        bot2.reply_to(message, "Invalid or unsupported URL. Supported platforms: YouTube, Instagram, Twitter, Facebook.")
        return

    try:
        bot2.reply_to(message, "Downloading media, please wait...")
        file_path = download_media(url)

        # Login to Mega.nz with user credentials
        mega_session = mega_login(username, password)
        if not mega_session:
            bot2.reply_to(message, "Failed to login to Mega.nz. Please check your username and password.")
            return

        # Upload to Mega.nz
        bot2.reply_to(message, "Uploading to Mega.nz...")
        uploaded_file = mega_session.upload(file_path)
        upload_link = mega_session.get_upload_link(uploaded_file)

        # Send Mega.nz link to the user
        bot2.reply_to(message, f"File uploaded to Mega.nz: {upload_link}")

        # Send the file back to the user
        with open(file_path, 'rb') as media:
            if file_path.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                bot2.send_photo(message.chat.id, media)
            elif file_path.lower().endswith('.mp4'):
                bot2.send_video(message.chat.id, media)
            else:
                bot2.send_document(message.chat.id, media)

        # Clean up
        os.remove(file_path)
        bot2.reply_to(message, "Download, upload, and sharing completed.")
    except Exception as e:
        logging.error("Download failed", exc_info=True)
        bot2.reply_to(message, f"Download failed: {str(e)}")

# Telegram command handlers
@bot2.message_handler(commands=['meganz'])
def handle_mega_login(message):
    try:
        # Expecting the format /meganz username password url
        args = message.text.split(maxsplit=3)
        if len(args) < 4:
            bot2.reply_to(message, "Usage: /meganz <username> <password> <URL>")
            return

        username = args[1]
        password = args[2]
        url = args[3]

        # Handle login and file upload
        download_and_upload_to_mega(message, url, username, password)

    except IndexError:
        bot2.reply_to(message, "Please provide valid arguments: /meganz <username> <password> <URL>.")

# Flask app setup
app = Flask(__name__)

@app.route('/' + API_TOKEN_2, methods=['POST'])
def bot_webhook():
    bot2.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "!", 200

@app.route('/')
def set_webhook():
    bot2.remove_webhook()
    bot2.set_webhook(url=os.getenv('KOYEB_URL') + '/' + API_TOKEN_2, timeout=60)
    return "Webhook set", 200

if __name__ == "__main__":
    # Run Flask app to handle incoming webhook requests
    app.run(host='0.0.0.0', port=8080, debug=True)