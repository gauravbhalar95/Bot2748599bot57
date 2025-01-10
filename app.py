import os
import logging
from flask import Flask, request
import telebot
import yt_dlp
import re
from urllib.parse import urlparse, parse_qs
from mega import Mega
import time
import instaloader

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

# Sanitize filenames for downloaded files
def sanitize_filename(filename, max_length=250):
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)
    return filename.strip()[:max_length]

# Mega login command
@bot2.message_handler(commands=['meganz'])
def handle_mega_login(message):
    global mega_client
    try:
        args = message.text.split(maxsplit=2)
        if len(args) == 1:
            # Perform anonymous login if no email and password are provided
            mega_client = Mega().login()  # Anonymous login
            bot2.reply_to(message, "Logged in to Mega.nz anonymously!")
        elif len(args) == 3:
            email = args[1]
            password = args[2]
            mega_client = Mega().login(email, password)
            bot2.reply_to(message, "Successfully logged in to Mega.nz!")
        else:
            bot2.reply_to(message, "Usage: /meganz <username> <password> or /meganz for anonymous login")
    except Exception as e:
        bot2.reply_to(message, f"Login failed: {str(e)}")

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

# Detect and handle Instagram profile URLs
@bot2.message_handler(func=lambda message: "instagram.com/" in message.text.lower())
def handle_instagram_profile_url(message):
    try:
        # Extract the username from the Instagram profile URL
        profile_url = message.text.strip()
        username = profile_url.rstrip('/').split('/')[-1]

        # Notify the user
        bot2.reply_to(message, f"Fetching posts for Instagram profile @{username}, please wait...")

        # Download Instagram posts
        result_message = download_instagram_posts(username)

        # Notify the user when the download is complete
        bot2.reply_to(message, result_message)
    except Exception as e:
        bot2.reply_to(message, f"An error occurred: {str(e)}")

# Function to download all posts from an Instagram profile using cookies
def download_instagram_posts(username):
    loader = instaloader.Instaloader()
    try:
        # Load cookies if available
        if os.path.exists(cookies_file):
            loader.load_session_from_file(username, cookies_file)
        else:
            bot2.reply_to(message, "No valid cookies found. Please log in to Instagram first.")
            return "Error: Cookies are required for login."

        # Set output directory
        profile_dir = os.path.join(output_dir, username)
        os.makedirs(profile_dir, exist_ok=True)

        # Download posts
        loader.download_profile(username, profile_pic=False, fast_update=True, download_stories=True)

        # Upload posts to Mega.nz
        if mega_client is None:
            raise Exception("Mega client is not logged in. Use /meganz <username> <password> to log in.")
        
        uploaded_links = []
        for root, dirs, files in os.walk(profile_dir):
            for file in files:
                file_path = os.path.join(root, file)
                uploaded_links.append(upload_to_mega(file_path))
        
        return f"All posts from @{username} have been downloaded and uploaded to Mega.nz. Links:\n" + "\n".join(uploaded_links)
    except Exception as e:
        logging.error("Error downloading Instagram posts", exc_info=True)
        return str(e)

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