import os
import logging
from flask import Flask, request
import telebot
import yt_dlp
import re
from urllib.parse import urlparse, parse_qs
from mega import Mega

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
SUPPORTED_DOMAINS = ['youtube.com', 'youtu.be', 'instagram.com', 'x.com', 'facebook.com']

# Mega client
mega_client = None
mega_logged_in = False

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

# Mega login command
@bot2.message_handler(commands=['meganz'])
def handle_mega_login(message):
    global mega_client, mega_logged_in
    if mega_logged_in:
        bot2.reply_to(message, "Already logged in to Mega.nz!")
        return

    args = message.text.split(maxsplit=2)

    try:
        if len(args) == 1:
            # Anonymous login
            mega_client = Mega().login()
        elif len(args) == 3:
            email, password = args[1], args[2]
            mega_client = Mega().login(email, password)
        else:
            bot2.reply_to(message, "Usage: /meganz <username> <password>")
            return

        mega_logged_in = True
        bot2.reply_to(message, "Successfully logged in to Mega.nz!")
    except Exception as e:
        bot2.reply_to(message, f"Login failed: {str(e)}")

# Logout command
@bot2.message_handler(commands=['logout'])
def handle_logout(message):
    global mega_client, mega_logged_in
    if not mega_logged_in:
        bot2.reply_to(message, "Not logged in to Mega.nz!")
        return

    mega_client = None
    mega_logged_in = False
    bot2.reply_to(message, "Logged out from Mega.nz.")

# Folder listing command
@bot2.message_handler(commands=['folder'])
def handle_folder_list(message):
    if not mega_logged_in:
        bot2.reply_to(message, "Please log in to Mega.nz first using /meganz.")
        return

    try:
        folders = mega_client.get_files()
        folder_list = "\n".join(f["a"]["n"] for f in folders.values() if f["t"] == 1)
        response = f"Available folders:\n{folder_list}" if folder_list else "No folders found."
        bot2.reply_to(message, response)
    except Exception as e:
        bot2.reply_to(message, f"Failed to list folders: {str(e)}")

# Download and upload using Mega.nz
@bot2.message_handler(commands=['mega'])
def handle_mega_command(message):
    if not mega_logged_in:
        bot2.reply_to(message, "Please log in to Mega.nz first using /meganz.")
        return

    args = message.text.split(maxsplit=2)
    if len(args) < 2:
        bot2.reply_to(message, "Usage: /mega <URL> [folder_name]")
        return

    url = args[1]
    folder_name = args[2] if len(args) > 2 else None
    handle_download_and_upload(message, url, upload_to_mega_flag=True, folder_name=folder_name)

# Handle download and upload with folder support
def handle_download_and_upload(message, url, upload_to_mega_flag, folder_name=None):
    if not is_valid_url(url):
        bot2.reply_to(message, "Invalid or unsupported URL. Supported platforms: YouTube, Instagram, Twitter, Facebook.")
        return

    try:
        bot2.reply_to(message, "Downloading the video, please wait...")

        # Download media
        file_path = download_media(url)

        if upload_to_mega_flag:
            # Upload to Mega.nz
            bot2.reply_to(message, "Uploading the video to Mega.nz, please wait...")
            mega_link = upload_to_mega(file_path, folder_name)
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