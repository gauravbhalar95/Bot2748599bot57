import os
import logging
from flask import Flask, request
import telebot
import yt_dlp
from mega import Mega
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import re
from urllib.parse import urlparse, parse_qs

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

# Mega clients dictionary to store multiple accounts
mega_accounts = {}

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
def upload_to_mega(file_path, account_name):
    if account_name not in mega_accounts:
        raise Exception(f"Mega account '{account_name}' not logged in.")

    try:
        mega_client = mega_accounts[account_name]
        folder = mega_client.find('my_mega_folder')
        if not folder:
            raise Exception("Folder 'my_mega_folder' not found.")

        # Upload the file to the folder
        file = mega_client.upload(file_path, folder[0])
        public_link = mega_client.get_upload_link(file)
        return public_link
    except Exception as e:
        logging.error("Error uploading to Mega", exc_info=True)
        raise


# Handle Mega account login
@bot2.message_handler(commands=['meganz'])
def handle_mega_login(message):
    try:
        args = message.text.split(maxsplit=3)
        if len(args) < 4:
            bot2.reply_to(message, "Usage: /meganz <account_name> <username> <password>")
            return

        account_name, username, password = args[1], args[2], args[3]
        mega_client = Mega().login(username, password)
        mega_accounts[account_name] = mega_client
        bot2.reply_to(message, f"Mega.nz account '{account_name}' successfully logged in!")
    except Exception as e:
        bot2.reply_to(message, f"Login failed: {str(e)}")


# Handle download and present account options for upload
def handle_download_and_present_accounts(message, url):
    try:
        bot2.reply_to(message, "Downloading the video, please wait...")

        # Download media
        file_path = download_media(url)

        # Create buttons for account selection
        markup = InlineKeyboardMarkup()
        for account_name in mega_accounts.keys():
            markup.add(InlineKeyboardButton(account_name, callback_data=f"upload:{account_name}:{file_path}"))

        bot2.reply_to(message, "Select the Mega.nz account for upload:", reply_markup=markup)
    except Exception as e:
        logging.error("Download failed", exc_info=True)
        bot2.reply_to(message, f"Download failed: {str(e)}")


# Callback handler for account selection and upload
@bot2.callback_query_handler(func=lambda call: call.data.startswith("upload:"))
def handle_account_selection(call):
    try:
        _, account_name, file_path = call.data.split(':')
        bot2.answer_callback_query(call.id, f"Uploading using account: {account_name}")
        bot2.edit_message_text("Uploading to Mega.nz, please wait...", chat_id=call.message.chat.id, message_id=call.message.id)

        # Upload file to the selected Mega.nz account
        public_link = upload_to_mega(file_path, account_name)
        bot2.edit_message_text(f"File uploaded successfully! Public link: {public_link}", chat_id=call.message.chat.id, message_id=call.message.id)

        # Cleanup
        os.remove(file_path)
    except Exception as e:
        logging.error("Upload failed", exc_info=True)
        bot2.edit_message_text(f"Upload failed: {str(e)}", chat_id=call.message.chat.id, message_id=call.message.id)


# Handle direct download requests
@bot2.message_handler(func=lambda message: True, content_types=['text'])
def handle_direct_download(message):
    url = message.text.strip()
    if is_valid_url(url):
        handle_download_and_present_accounts(message, url)
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