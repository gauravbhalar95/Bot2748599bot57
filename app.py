import os
import logging
from flask import Flask, request
import telebot
import yt_dlp
import re
import subprocess
from urllib.parse import urlparse, parse_qs
from mega import Mega
import time
import json

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
SUPPORTED_DOMAINS = ['youtube.com', 'youtu.be', 'instagram.com', 'x.com', 'facebook.com', 'xvideo.com', 'xnxx.com']

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


# Mega login command with checks to allow login only once
@bot2.message_handler(commands=['meganz'])
def handle_mega_login(message):
    global mega_client
    try:
        if mega_client is not None:
            bot2.reply_to(message, "You are already logged in to Mega.nz.")
            return
        
        args = message.text.split(maxsplit=2)
        if len(args) == 1:
            # Perform anonymous login if no email and password are provided
            mega_client = Mega().login()  # Anonymous login
            bot2.reply_to(message, "Logged in to Mega.nz anonymously!")
        elif len(args) == 3:
            # Perform login using email and password with retries
            email = args[1]
            password = args[2]
            retries = 3
            for attempt in range(retries):
                try:
                    mega_client = Mega().login(email, password)
                    bot2.reply_to(message, "Successfully logged in to Mega.nz!")
                    break  # Exit the loop if login is successful
                except Exception as e:
                    if "Expecting value" in str(e):
                        bot2.reply_to(message, f"Login attempt {attempt + 1} failed: Invalid server response. Retrying...")
                        time.sleep(5)  # Wait 5 seconds before retrying
                    else:
                        bot2.reply_to(message, f"Login attempt {attempt + 1} failed: {str(e)}")
                        break  # Exit the loop if it's not a JSONDecodeError
        else:
            bot2.reply_to(message, "Usage: /meganz <username> <password> or /meganz for anonymous login")

    except Exception as e:
        bot2.reply_to(message, f"Login failed: {str(e)}")


# Mega logout command
@bot2.message_handler(commands=['logout'])
def handle_logout(message):
    global mega_client
    try:
        if mega_client is None:
            bot2.reply_to(message, "You are not logged in to Mega.nz.")
        else:
            mega_client.logout()
            mega_client = None  # Reset the mega_client
            bot2.reply_to(message, "Logged out from Mega.nz successfully.")
    except Exception as e:
        bot2.reply_to(message, f"Logout failed: {str(e)}")
# Mega download and upload handler remains the same as before
@bot2.message_handler(commands=['mega'])
def handle_mega(message):
    try:
        args = message.text.split(maxsplit=2)  # Split into at most 3 parts
        if len(args) < 2:
            bot2.reply_to(message, "Usage: /mega <URL> [folder]\nExample: /mega https://mega.nz/folder/abc123")
            return

        url = args[1]  # Mega.nz folder or file URL
        folder = args[2] if len(args) > 2 else None  # Optional folder name

        # Pass the URL and folder to the download/upload handler
        handle_download_and_upload(message, url, folder, upload_to_mega_flag=True)
    except Exception as e:
        bot2.reply_to(message, f"Error: {str(e)}")

@bot.message_handler(commands=['folder'])
def get_files_from_folder(message):
    try:
        # Parse the folder URL from the message
        folder_url = message.text.split(' ', 1)[1]  # The folder URL should be after the command
        bot2.send_message(message.chat.id, "Fetching files and account details...")
        
        # Get account info
        account_info = mega_client.get_user()
        account_name = account_info['name']
        account_email = account_info['email']
        storage_info = mega_client.get_storage_space()
        total_space = storage_info['total'] / (1024 * 1024 * 1024)  # Convert to GB
        used_space = storage_info['used'] / (1024 * 1024 * 1024)    # Convert to GB

        # Get files from the folder
        folder = mega_client.folder(folder_url)
        files = mega_client.get_files(folder)
        
        # Format the account details
        account_details = (
            f"**Account Information:**\n"
            f"Name: {account_name}\n"
            f"Email: {account_email}\n"
            f"Storage Used: {used_space:.2f} GB / {total_space:.2f} GB\n\n"
        )

        # Format the file list
        file_list = "**Files in the folder:**\n\n"
        for file_id, file_info in files.items():
            file_list += f"Name: {file_info['a']['n']}\nSize: {file_info['s']} bytes\n\n"

        # Send account and file information
        response = account_details + (file_list if file_list.strip() else "No files found in the folder.")
        bot2.send_message(message.chat.id, response, parse_mode='Markdown')
    except IndexError:
        bot2.send_message(message.chat.id, "Please provide a valid folder URL after the command.")
    except Exception as e:
        bot2.send_message(message.chat.id, f"An error occurred: {e}")


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