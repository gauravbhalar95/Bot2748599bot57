import os
import re
import logging
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, request
import yt_dlp
from telebot import TeleBot, types

# Environment variables
api_token_2 = os.getenv("API_TOKEN_2")
output_dir = "./downloads/"
cookies_file = "cookies.txt"
webhook_url = os.getenv("WEBHOOK_URL")
bot2 = TeleBot(api_token_2)

# Flask app
app = Flask(__name__)

# Ensure output directory exists
os.makedirs(output_dir, exist_ok=True)

def sanitize_filename(filename):
    """Sanitize filename to avoid issues with special characters."""
    return re.sub(r'[^a-zA-Z0-9_.-]', '_', filename)

def is_valid_url(url):
    """Check if the provided URL is valid."""
    return re.match(r'^(https?://)', url) is not None

def download_media(url, username=None, password=None, start_time=None, end_time=None):
    logging.debug(f"Attempting to download media from URL: {url} with start_time: {start_time}, end_time: {end_time}")

    # Set up options for yt-dlp
    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'outtmpl': f'{output_dir}{sanitize_filename("%(title)s")}.%(ext)s',
        'cookiefile': cookies_file,
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }],
        'socket_timeout': 10,
        'retries': 5,
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.85 Safari/537.36',
    }

    # Add time range if specified
    if start_time and end_time:
        ydl_opts['download_sections'] = [f"*{start_time}-{end_time}"]

    if username and password:
        ydl_opts['username'] = username
        ydl_opts['password'] = password

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info_dict)

        if not os.path.exists(file_path):
            part_file_path = f"{file_path}.part"
            if os.path.exists(part_file_path):
                os.rename(part_file_path, file_path)
                logging.debug(f"Renamed partial file: {part_file_path} to {file_path}")
            else:
                logging.error(f"Downloaded file not found at path: {file_path}")
                raise Exception("Download failed: File not found after download.")

        return file_path

    except Exception as e:
        logging.error(f"yt-dlp download error: {str(e)}")
        raise

def download_and_send(message, url, username=None, password=None):
    # Parse the message for start and end times if provided
    time_match = re.search(r"\?start=(\d+)&end=(\d+)", url)
    start_time, end_time = None, None
    if time_match:
        start_time = time_match.group(1)
        end_time = time_match.group(2)

    if not is_valid_url(url):
        bot2.reply_to(message, "The provided URL is not valid. Please enter a valid URL.")
        return

    try:
        bot2.reply_to(message, "Downloading media, this may take some time...")
        logging.debug("Initiating media download")

        with ThreadPoolExecutor(max_workers=3) as executor:
            future = executor.submit(download_media, url, username, password, start_time, end_time)
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

@bot2.message_handler(commands=['download'])
def handle_download(message):
    try:
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            bot2.reply_to(message, "Please provide a valid URL after the /download command.")
            return

        url = args[1]
        download_and_send(message, url)
    except Exception as e:
        logging.error(f"Error handling download command: {str(e)}")

@app.route(f"/{api_token_2}", methods=['POST'])
def webhook():
    json_string = request.get_data().decode('utf-8')
    update = types.Update.de_json(json_string)
    bot2.process_new_updates([update])
    return "", 200

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    bot2.remove_webhook()
    bot2.set_webhook(url=webhook_url)
    app.run(host="0.0.0.0", port=8080)
