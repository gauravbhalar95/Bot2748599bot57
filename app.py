import os
import logging
import threading
from flask import Flask, request
import telebot
import yt_dlp
from concurrent.futures import ThreadPoolExecutor
import requests
from PIL import Image
from io import BytesIO

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

# Function to sanitize filenames
def sanitize_filename(filename, max_length=200):
    import re
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)
    return filename.strip()[:max_length]

# Function to download media
def download_media(url, username=None, password=None):
    logging.debug(f"Attempting to download media from URL: {url}")

    # Set up options for yt-dlp
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best',  # Try highest quality video and audio
        'outtmpl': f'{output_dir}%(title)s.%(ext)s',  # Save path for media files
        'cookiefile': cookies_file,  # Use cookie file if required for authentication
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }],
        'socket_timeout': 15,
        'retries': 5,  # Retry on download errors
    }

    # Instagram login, if credentials are provided
    if username and password:
        ydl_opts['username'] = username
        ydl_opts['password'] = password

    # Add specific logging for URL types
    if 'instagram.com' in url:
        logging.debug("Processing Instagram URL")
    elif 'twitter.com' in url or 'x.com' in url:
        logging.debug("Processing Twitter/X URL")
    elif 'youtube.com' in url or 'youtu.be' in url:
        logging.debug("Processing YouTube URL")
        ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best'
    elif 'facebook.com' in url:
        logging.debug("Processing Facebook URL")
    else:
        logging.error(f"Unsupported URL: {url}")
        raise Exception("Unsupported URL!")

    try:
        # Attempt the download
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info_dict)

        # Confirm if the file exists after download
        if not os.path.exists(file_path):
            part_file_path = f"{file_path}.part"
            if os.path.exists(part_file_path):
                # If the .part file exists, rename it to the final file
                os.rename(part_file_path, file_path)
                logging.debug(f"Renamed partial file: {part_file_path} to {file_path}")
            else:
                logging.error(f"Downloaded file not found at path: {file_path}")
                raise Exception("Download failed: File not found after download.")

        return file_path

    except Exception as e:
        logging.error(f"yt-dlp download error: {str(e)}")
        raise

# Function to download media and send it asynchronously
def download_and_send(message, url, username=None, password=None):
    try:
        bot2.reply_to(message, "Downloading media, this may take some time...")

        with ThreadPoolExecutor(max_workers=3) as executor:
            future = executor.submit(download_media, url, username, password)
            file_path = future.result()

            with open(file_path, 'rb') as media:
                if file_path.lower().endswith(('.mp4', '.mkv', '.webm')):
                    bot2.send_video(message.chat.id, media)
                elif file_path.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                    bot2.send_photo(message.chat.id, media)
                else:
                    bot2.send_document(message.chat.id, media)

            os.remove(file_path)

    except Exception as e:
        bot2.reply_to(message, f"Failed to download. Error: {str(e)}")
        logging.error(f"Download failed: {e}")

# Function to download Instagram media
def download_instagram_media(url, username=None, password=None):
    try:
        logging.debug(f"Attempting to download Instagram media from URL: {url}")

        # Set up headers for Instagram API
        headers = {
            'User-Agent': 'Instagram 154.0.0.39.118 Android (#129)',
            'Accept': '*/*',
            'Accept-Encoding': 'gzip, deflate',
            'Accept-Language': 'en-US,en;q=0.9',
            'X-IG-App-ID': '154354653489596',
            'X-IG-Capabilities': '3brTvwA=',
            'X-IG-Connection-Type': 'WIFI',
        }

        # Make a GET request to the Instagram API
        response = requests.get(url, headers=headers)

        # Check if the response was successful
        if response.status_code == 200:
            # Get the media URL from the response
            media_url = response.json()['graphql']['shortcode_media']['display_url']

            # Download the media
            media_response = requests.get(media_url, headers=headers)

            # Check if the media download was successful
            if media_response.status_code == 200:
                # Save the media to a file
                with open(f'{output_dir}{sanitize_filename(media_url)}.jpg', 'wb') as media_file:
                    media_file.write(media_response.content)

                # Send the media to the user
                with open(f'{output_dir}{sanitize_filename(media_url)}.jpg', 'rb') as media_file:
                    bot2.send_photo(message.chat.id, media_file)

                # Remove the media file
                os.remove(f'{output_dir}{sanitize_filename(media_url)}.jpg')
            else:
                logging.error(f"Failed to download Instagram media: {media_response.status_code}")
        else:
            logging.error(f"Failed to download Instagram media: {response.status_code}")

    except Exception as e:
        logging.error(f"Failed to download Instagram media: {str(e)}")

# Function to download Twitter media
def download_twitter_media(url, username=None, password=None):
    try:
        logging.debug(f"Attempting to download Twitter media from URL: {url}")

        # Set up headers for Twitter API
        headers = {
            'User-Agent': 'Twitter 12.18.0 Android (#101)',
            'Accept': '*/*',
            'Accept-Encoding': 'gzip, deflate',
            'Accept-Language': 'en-US,en;q=0.9',
            'X-Twitter-Client': 'Twitter for Android',
            'X-Twitter-Client-Version': '12.18.0',
        }

        # Make a GET request to the Twitter API
        response = requests.get(url, headers=headers)

        # Check if the response was successful
        if response.status_code == 200:
            # Get the media URL from the response
            media_url = response.json()['includes']['media'][0]['media_url']

            # Download the media
            media_response = requests.get(media_url, headers=headers)

            # Check if the media download was successful
            if media_response.status_code == 200:
                # Save the media to a file
                with open(f'{output_dir}{sanitize_filename(media_url)}.jpg', 'wb') as media_file:
                    media_file.write(media_response.content)

                # Send the media to the user
                with open(f'{output_dir}{sanitize_filename(media_url)}.jpg', 'rb') as media_file:
                    bot2.send_photo(message.chat.id, media_file)

                # Remove the media file
                os.remove(f'{output_dir}{sanitize_filename(media_url)}.jpg')
            else:
                logging.error(f"Failed to download Twitter media: {media_response.status_code}")
        else:
            logging.error(f"Failed to download Twitter media: {response.status_code}")

    except Exception as e:
        logging.error(f"Failed to download Twitter media: {str(e)}")

# Function to download Facebook media
def download_facebook_media(url, username=None, password=None):
    try:
        logging.debug(f"Attempting to download Facebook media from URL: {url}")

        # Set up headers for Facebook API
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.169 Safari/537.3',
            'Accept': '*/*',
            'Accept-Encoding': 'gzip, deflate',
            'Accept-Language': 'en-US,en;q=0.9',
        }

        # Make a GET request to the Facebook API
        response = requests.get(url, headers=headers)

        # Check if the response was successful
        if response.status_code == 200:
            # Get the media URL from the response
            media_url = response.json()['data']['media']['image']['url']

            # Download the media
            media_response = requests.get(media_url, headers=headers)

            # Check if the media download was successful
            if media_response.status_code == 200:
                # Save the media to a file
                with open(f'{output_dir}{sanitize_filename(media_url)}.jpg', 'wb') as media_file:
                    media_file.write(media_response.content)

                # Send the media to the user
                with open(f'{output_dir}{sanitize_filename(media_url)}.jpg', 'rb') as media_file:
                    bot2.send_photo(message.chat.id, media_file)

                # Remove the media file
                os.remove(f'{output_dir}{sanitize_filename(media_url)}.jpg')
            else:
                logging.error(f"Failed to download Facebook media: {media_response.status_code}")
        else:
            logging.error(f"Failed to download Facebook media: {response.status_code}")

    except Exception as e:
        logging.error(f"Failed to download Facebook media: {str(e)}")

# Function to handle messages
@bot2.message_handler(func=lambda message: True)
def handle_links(message):
    url = message.text

    # Extract Instagram credentials if provided in the message
    username = None
    password = None
    if "@" in url:  # Example: url containing "username:password"
        username, password = url.split('@', 1)  # Assuming format: username:password@url
        url = password  # Change url to actual URL

    # Check if the URL is an Instagram media URL
    if 'instagram.com' in url:
        # Download and send the media
        download_instagram_media(url, username, password)
    # Check if the URL is a Twitter media URL
    elif 'twitter.com' in url or 'x.com' in url:
        # Download and send the media
        download_twitter_media(url, username, password)
    # Check if the URL is a Facebook media URL
    elif 'facebook.com' in url:
        # Download and send the media
        download_facebook_media(url, username, password)
    # Check if the URL is a YouTube media URL
    elif 'youtube.com' in url or 'youtu.be' in url:
        # Download and send the media
        download_and_send(message, url, username, password)
    else:
        # Download and send the media
        download_and_send(message, url, username, password)

# Flask app setup
app = Flask(__name__)

# Flask routes for webhook handling
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
    # Run the Flask app in debug mode
    app.run(host='0.0.0.0', port=8080, debug=True)