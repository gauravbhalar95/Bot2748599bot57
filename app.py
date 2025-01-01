import os
import logging
from flask import Flask, request
import telebot
import yt_dlp
import re
from urllib.parse import urlparse, parse_qs
from mega import Mega

# Load environment variables
API_TOKEN_2 = os.getenv('API_TOKEN_2')  # Your Telegram Bot API Token
KOYEB_URL = os.getenv('KOYEB_URL')  # Webhook URL for deployment
output_dir = 'downloads/'  # Download directory

# Initialize bot and logging
bot2 = telebot.TeleBot(API_TOKEN_2, parse_mode='HTML')
logging.basicConfig(level=logging.DEBUG)

# Mega clients dictionary for multi-account
mega_clients = {}

# Supported domains
SUPPORTED_DOMAINS = ['youtube.com', 'youtu.be', 'instagram.com', 'x.com', 'twitter.com', 'facebook.com']

# Ensure download directory exists
if not os.path.exists(output_dir):
    os.makedirs(output_dir)


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


# Get the direct download URL
def fetch_direct_download_url(url):
    ydl_opts = {'quiet': True, 'skip_download': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            return info_dict.get('url', None)
    except Exception as e:
        logging.error(f"Error fetching direct URL: {e}", exc_info=True)
        return None


# Mega.nz Login Handler
@bot2.message_handler(commands=['meganz'])
def handle_mega_login(message):
    global mega_clients
    args = message.text.split(maxsplit=3)
    if len(args) == 4:
        account_name, email, password = args[1], args[2], args[3]
        try:
            mega_client = Mega().login(email, password)
            mega_clients[account_name] = mega_client
            bot2.reply_to(message, f"Logged into Mega.nz as {account_name} successfully!")
        except Exception as e:
            bot2.reply_to(message, f"Login failed: {str(e)}")
    else:
        bot2.reply_to(message, "Usage: /meganz <account_name> <email> <password>")


# Handle video download and upload
@bot2.message_handler(commands=['mega'])
def handle_mega_command(message):
    args = message.text.split(maxsplit=3)
    if len(args) < 3:
        bot2.reply_to(message, "Usage: /mega <account_name> <URL> <folder_name>")
        return

    account_name, url, folder_name = args[1], args[2], args[3]
    if account_name not in mega_clients:
        bot2.reply_to(message, f"Account '{account_name}' not found. Please log in using /meganz first.")
        return

    if not is_valid_url(url):
        bot2.reply_to(message, "Invalid URL. Supported platforms: YouTube, Instagram, Twitter, Facebook.")
        return

    bot2.reply_to(message, "Downloading the video, please wait...")
    try:
        # Download video
        ydl_opts = {
            'format': 'best[ext=mp4]/best',
            'outtmpl': f'{output_dir}{sanitize_filename("%(title)s")}.%(ext)s',
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info_dict)

        # Upload to Mega.nz
        bot2.reply_to(message, "Uploading the video to Mega.nz, please wait...")
        mega_client = mega_clients[account_name]
        folder = mega_client.find(folder_name)
        if not folder:
            folder = mega_client.create_folder(folder_name)
        file = mega_client.upload(file_path, folder[0])
        mega_link = mega_client.get_upload_link(file)

        if mega_link:
            bot2.reply_to(message, f"Video uploaded to Mega.nz: {mega_link}")
        else:
            bot2.reply_to(message, "Failed to upload the video to Mega.nz.")
    except Exception as e:
        logging.error(f"Error in /mega command: {e}", exc_info=True)
        bot2.reply_to(message, f"Error: {str(e)}")


# Handle direct download URL fetch
@bot2.message_handler(func=lambda message: True, content_types=['text'])
def handle_direct_download(message):
    url = message.text.strip()
    if is_valid_url(url):
        bot2.reply_to(message, "Fetching direct download URL...")
        direct_url = fetch_direct_download_url(url)
        if direct_url:
            bot2.reply_to(message, f"Direct download URL: {direct_url}")
        else:
            bot2.reply_to(message, "Failed to fetch the direct download URL.")
    else:
        bot2.reply_to(message, "Invalid URL. Please provide a valid link.")


# Flask app for webhook
app = Flask(__name__)

@app.route('/' + API_TOKEN_2, methods=['POST'])
def bot_webhook():
    bot2.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "!", 200


@app.route('/')
def set_webhook():
    bot2.remove_webhook()
    bot2.set_webhook(url=KOYEB_URL + '/' + API_TOKEN_2)
    return "Webhook set", 200


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080, debug=True)