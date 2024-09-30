import os
import logging
import requests
from flask import Flask, request
import telebot
import yt_dlp
from concurrent.futures import ThreadPoolExecutor

# Load API tokens and other configurations from environment variables
API_TOKEN = os.getenv('API_TOKEN')  # Your bot token
KOYEB_URL = os.getenv('KOYEB_URL')  # Koyeb deployment URL
INSTAGRAM_USERNAME = os.getenv('INSTAGRAM_USERNAME')  # Instagram username
INSTAGRAM_PASSWORD = os.getenv('INSTAGRAM_PASSWORD')  # Instagram password
COOKIES_FILE = os.getenv('COOKIES_FILE', 'cookies.txt')  # Kiwi Browser cookies file path

# Initialize the bot
bot = telebot.TeleBot(API_TOKEN)

# Directory to save downloaded files
output_dir = 'downloads/'

# Create the downloads directory if it does not exist
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# Logging setup
logging.basicConfig(level=logging.DEBUG)

# Function to sanitize filenames
def sanitize_filename(filename, max_length=200):
    import re
    filename = re.sub(r'[\\/*?:"<>|]', "_", filename)
    filename = re.sub(r'https?://\S+', '', filename)  # Remove URLs from the filename
    filename = filename.strip()[:max_length]
    return filename

# Function to login to Instagram and save cookies
def login_instagram():
    session = requests.Session()
    login_url = 'https://www.instagram.com/accounts/login/ajax/'
    session.headers.update({'User-Agent': 'Mozilla/5.0'})
    
    # Retrieve CSRF token
    session.get('https://www.instagram.com')
    csrf_token = session.cookies.get('csrftoken')
    
    session.headers.update({'X-CSRFToken': csrf_token})
    payload = {
        'username': INSTAGRAM_USERNAME,
        'password': INSTAGRAM_PASSWORD,
    }
    
    # Login
    response = session.post(login_url, data=payload)
    if response.status_code == 200 and response.json().get('authenticated'):
        logging.info("Successfully logged into Instagram.")
        # Save cookies to a file
        with open(COOKIES_FILE, 'w') as f:
            for cookie in session.cookies:
                f.write(f"{cookie.name}={cookie.value}\n")
        return True
    else:
        logging.error("Failed to log into Instagram.")
        return False

# Function to download media from Instagram
def download_instagram(url):
    logging.info(f"Downloading from Instagram: {url}")
    ydl_opts = {
        'format': 'best',
        'outtmpl': f'{output_dir}%(title)s.%(ext)s',
        'cookiefile': COOKIES_FILE,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

# Function to download media from Twitter
def download_twitter(url):
    logging.info(f"Downloading from Twitter: {url}")
    ydl_opts = {
        'format': 'best',
        'outtmpl': f'{output_dir}%(title)s.%(ext)s',
        'cookiefile': COOKIES_FILE,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

# Function to download media from Facebook
def download_facebook(url):
    logging.info(f"Downloading from Facebook: {url}")
    ydl_opts = {
        'format': 'best',
        'outtmpl': f'{output_dir}%(title)s.%(ext)s',
        'cookiefile': COOKIES_FILE,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

# Function to download media from YouTube
def download_youtube(url):
    logging.info(f"Downloading from YouTube: {url}")
    ydl_opts = {
        'format': 'best',
        'outtmpl': f'{output_dir}%(title)s.%(ext)s',
        'cookiefile': COOKIES_FILE,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

# Function to send media to the user
def send_media(message, file_path):
    with open(file_path, 'rb') as media:
        if file_path.lower().endswith(('.mp4', '.mkv', '.webm')):
            bot.send_video(message.chat.id, media)
        elif file_path.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
            bot.send_photo(message.chat.id, media)
        else:
            bot.send_document(message.chat.id, media)

# Function to handle links and download media
def handle_links(message):
    url = message.text
    try:
        if 'instagram.com' in url:
            if not os.path.exists(COOKIES_FILE):
                login_instagram()
            download_instagram(url)
            send_media(message, output_dir + sanitize_filename(url) + '.mp4')
        elif 'twitter.com' in url:
            download_twitter(url)
            send_media(message, output_dir + sanitize_filename(url) + '.mp4')
        elif 'facebook.com' in url:
            download_facebook(url)
            send_media(message, output_dir + sanitize_filename(url) + '.mp4')
        elif 'youtube.com' in url or 'youtu.be' in url:
            download_youtube(url)
            send_media(message, output_dir + sanitize_filename(url) + '.mp4')
        else:
            bot.reply_to(message, "Unsupported URL. Please send a valid media link.")
    except Exception as e:
        bot.reply_to(message, f"Failed to download media. Error: {str(e)}")
        logging.error(f"Download error: {str(e)}")

# Flask app setup
app = Flask(__name__)

# Bot commands and handlers
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Welcome! To download media from Instagram, Twitter, Facebook, or YouTube, please send the link you want to download.")

# Handle media links automatically
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    handle_links(message)

# Flask routes for webhook handling
@app.route('/' + API_TOKEN, methods=['POST'])
def getMessage():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "!", 200

@app.route('/')
def webhook():
    bot.remove_webhook()
    webhook_url = f'https://{KOYEB_URL}/{API_TOKEN}'
    bot.set_webhook(url=webhook_url)
    logging.info(f"Webhook set to {webhook_url}")
    return "Webhook set", 200

if __name__ == '__main__':
    # Log into Instagram
    login_instagram()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
