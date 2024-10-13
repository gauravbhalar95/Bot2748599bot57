import os
import logging
import threading
from flask import Flask, request
import telebot
import yt_dlp
from concurrent.futures import ThreadPoolExecutor
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive

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

# Google Drive authentication setup
gauth = GoogleAuth()
gauth.LocalWebserverAuth()  # Authenticate locally (for testing)
drive = GoogleDrive(gauth)

# Function to sanitize filenames
def sanitize_filename(filename, max_length=200):
    import re
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)
    return filename.strip()[:max_length]

# Function to download media
def download_media(url, username=None, password=None):
    logging.debug(f"Attempting to download media from URL: {url}")

    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',  # Download best video and audio
        'outtmpl': f'{output_dir}%(title)s.%(ext)s',
        'merge_output_format': 'mp4',
        'cookiefile': cookies_file,
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }],
        'ffmpeg_location': '/bin/ffmpeg',
        'socket_timeout': 10,
        'retries': 5,
        'max_filesize': 2 * 1024 * 1024 * 1024,  # Max size 2GB
    }

    # Handle Instagram, Twitter, YouTube, etc.
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info_dict)
        return file_path

    except Exception as e:
        logging.error(f"yt-dlp download error: {str(e)}")
        raise

# Function to convert video to audio
def convert_to_audio(file_path):
    try:
        audio_file = file_path.rsplit('.', 1)[0] + ".mp3"  # Create an MP3 filename
        os.system(f'ffmpeg -i "{file_path}" "{audio_file}"')
        return audio_file
    except Exception as e:
        logging.error(f"Audio conversion error: {e}")
        raise

# Function to upload file to Google Drive
def upload_to_google_drive(file_path):
    try:
        file_drive = drive.CreateFile({'title': os.path.basename(file_path)})
        file_drive.SetContentFile(file_path)
        file_drive.Upload()
        logging.info(f"File uploaded: {file_path}")
        return file_drive['alternateLink']
    except Exception as e:
        logging.error(f"Google Drive upload error: {e}")
        raise

# Function to download and send the audio
def download_audio_and_send(message, url):
    try:
        bot2.reply_to(message, "Downloading and converting to audio...")
        file_path = download_media(url)

        # Convert to audio
        audio_file = convert_to_audio(file_path)

        # Send audio file
        with open(audio_file, 'rb') as audio:
            bot2.send_audio(message.chat.id, audio)

        # Clean up
        os.remove(file_path)
        os.remove(audio_file)

    except Exception as e:
        bot2.reply_to(message, f"Failed to download and convert to audio. Error: {e}")

# Function to download and upload to Google Drive
def download_and_upload_drive(message, url):
    try:
        bot2.reply_to(message, "Downloading and uploading to Google Drive...")
        file_path = download_media(url)

        # Upload to Google Drive
        drive_link = upload_to_google_drive(file_path)
        bot2.reply_to(message, f"File uploaded successfully: {drive_link}")

        # Clean up
        os.remove(file_path)

    except Exception as e:
        bot2.reply_to(message, f"Failed to upload to Google Drive. Error: {e}")

# Command handler for /audio
@bot2.message_handler(commands=['audio'])
def handle_audio(message):
    url = message.text.split()[1]  # Expecting URL after /audio command
    threading.Thread(target=download_audio_and_send, args=(message, url)).start()

# Command handler for /drive
@bot2.message_handler(commands=['drive'])
def handle_drive(message):
    url = message.text.split()[1]  # Expecting URL after /drive command
    threading.Thread(target=download_and_upload_drive, args=(message, url)).start()

# Flask app setup
app = Flask(__name__)

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
