import os
import logging
from flask import Flask, request
import telebot
import requests
from urllib.parse import urlparse
import re

# Load environment variables
API_TOKEN_2 = os.getenv('API_TOKEN_2')  # Telegram bot token
CHANNEL_ID = os.getenv('CHANNEL_ID')   # Example: '@YourChannel'
KOYEB_URL = os.getenv('KOYEB_URL')     # Koyeb public URL for webhook
HIKER_API_TOKEN = os.getenv('HIKER_API_TOKEN')  # Hiker API token for Instagram downloads

# Initialize bot
bot2 = telebot.TeleBot(API_TOKEN_2, parse_mode='HTML')

# Directory for downloaded files
output_dir = 'downloads/'

# Ensure the downloads directory exists
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# Logging configuration
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Supported domains for validation
SUPPORTED_DOMAINS = ['youtube.com', 'youtu.be', 'instagram.com', 'x.com', 'facebook.com']

# Sanitize filenames to ensure valid file paths
def sanitize_filename(filename, max_length=250):
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)  # Remove invalid characters
    return filename.strip()[:max_length]             # Limit length

# Handle Instagram-specific downloads using the Hiker API
@bot2.message_handler(func=lambda message: 'instagram.com' in message.text.lower(), content_types=['text'])
def handle_instagram_auto(message):
    url = message.text.strip()

    # Validate the Instagram URL
    if not url.startswith("https://www.instagram.com/"):
        bot2.reply_to(message, "Invalid Instagram URL. Please provide a valid Instagram post or reel link.")
        return

    try:
        bot2.reply_to(message, "Downloading from Instagram using the Hiker API. Please wait...")

        # Hiker API endpoint and request setup
        hiker_api_url = "https://api.hiker.example/download"  # Replace with the actual Hiker API endpoint
        headers = {"Authorization": f"Bearer {HIKER_API_TOKEN}"}
        params = {"url": url}

        # API request
        response = requests.get(hiker_api_url, headers=headers, params=params)

        if response.status_code == 200:
            result = response.json()
            media_url = result.get('media_url')  # Extract the media URL

            if media_url:
                # Download the media
                media_response = requests.get(media_url, stream=True)
                if media_response.status_code == 200:
                    file_extension = media_url.split('.')[-1]
                    file_name = f"{output_dir}{sanitize_filename('instagram_media')}.{file_extension}"

                    # Save the file locally
                    with open(file_name, 'wb') as media_file:
                        for chunk in media_response.iter_content(chunk_size=1024):
                            media_file.write(chunk)

                    # Send the file to the user
                    with open(file_name, 'rb') as media:
                        if file_extension in ['mp4', 'mov']:
                            bot2.send_video(message.chat.id, media)
                        else:
                            bot2.send_photo(message.chat.id, media)

                    # Cleanup
                    os.remove(file_name)
                else:
                    bot2.reply_to(message, "Failed to download media from the provided link.")
            else:
                bot2.reply_to(message, "Media URL not found in the API response.")
        else:
            bot2.reply_to(message, f"Hiker API error: {response.status_code}, {response.text}")

    except Exception as e:
        logging.error("Error downloading Instagram media using the Hiker API", exc_info=True)
        bot2.reply_to(message, f"An error occurred while processing your request: {str(e)}")

# Flask app for webhook
app = Flask(__name__)

@app.route('/' + API_TOKEN_2, methods=['POST'])
def bot_webhook():
    """
    Webhook endpoint to process updates from Telegram.
    """
    bot2.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "OK", 200

@app.route('/')
def set_webhook():
    """
    Sets the webhook for the bot using the Koyeb public URL.
    """
    bot2.remove_webhook()
    bot2.set_webhook(url=KOYEB_URL + '/' + API_TOKEN_2, timeout=60)
    return "Webhook set successfully!", 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080, debug=True)