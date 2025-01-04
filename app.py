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
CHANNEL_ID = os.getenv('CHANNEL_ID')
KOYEB_URL = os.getenv('KOYEB_URL')

bot2 = telebot.TeleBot(API_TOKEN_2, parse_mode='HTML')

output_dir = 'downloads/'
cookies_file = 'cookies.txt'

if not os.path.exists(output_dir):
    os.makedirs(output_dir)

logging.basicConfig(level=logging.DEBUG)

SUPPORTED_DOMAINS = ['youtube.com', 'youtu.be', 'instagram.com', 'x.com', 'facebook.com']

mega_client = None

def sanitize_filename(filename, max_length=250):
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)
    return filename.strip()[:max_length]

def is_valid_url(url):
    try:
        result = urlparse(url)
        return result.scheme in ['http', 'https'] and any(domain in result.netloc for domain in SUPPORTED_DOMAINS)
    except ValueError:
        return False

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

def upload_to_mega(file_path, folder_name=None):
    if mega_client is None:
        raise Exception("Mega client is not logged in.")
    try:
        if folder_name:
            folders = mega_client.find(folder_name)
            if not folders:
                folder = mega_client.create_folder(folder_name)
            else:
                folder = folders[0]
            file = mega_client.upload(file_path, folder)
        else:
            file = mega_client.upload(file_path)
        return mega_client.get_upload_link(file)
    except Exception as e:
        logging.error("Error uploading to Mega", exc_info=True)
        raise

def get_storage_space():
    if mega_client is None:
        raise Exception("Mega client is not logged in.")
    try:
        space = mega_client.get_storage_space(kilo=True)
        used_space = space['used']
        total_space = space['total']
        return f"Storage used: {used_space} KB, Total: {total_space} KB"
    except Exception as e:
        logging.error("Error retrieving storage space", exc_info=True)
        raise

# Mega login command
@bot2.message_handler(commands=['meganz'])
def handle_mega_login(message):
    global mega_client
    args = message.text.split(maxsplit=2)

    try:
        if mega_client:
            bot2.reply_to(message, "Already logged in to Mega.nz!")
            return

        if len(args) == 1:
            mega_client = Mega().login()
            bot2.reply_to(message, "Logged in to Mega.nz anonymously!")
        elif len(args) == 3:
            email, password = args[1], args[2]
            mega_client = Mega().login(email, password)
            bot2.reply_to(message, "Successfully logged in to Mega.nz!")
        else:
            bot2.reply_to(message, "Usage: /meganz <username> <password>")
    except Exception as e:
        bot2.reply_to(message, f"Login failed: {str(e)}")

# Logout from Mega
@bot2.message_handler(commands=['logout'])
def handle_mega_logout(message):
    global mega_client
    if not mega_client:
        bot2.reply_to(message, "Not logged in to Mega.nz!")
        return
    mega_client = None
    bot2.reply_to(message, "Logged out of Mega.nz!")

# List all folders
@bot2.message_handler(commands=['folder'])
def handle_list_folders(message):
    if not mega_client:
        bot2.reply_to(message, "Mega.nz is not logged in!")
        return

    try:
        folders = mega_client.get_files_in_node(mega_client.get_node_by_type(2))  # Root directory
        folder_list = [f"<b>{folder['a']['n']}</b>" for folder in folders.values() if folder['t'] == 1]
        if folder_list:
            bot2.reply_to(message, "\n".join(folder_list), parse_mode='HTML')
        else:
            bot2.reply_to(message, "No folders found!")
    except Exception as e:
        bot2.reply_to(message, f"Failed to fetch folders: {str(e)}")

# Other commands remain unchanged...

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