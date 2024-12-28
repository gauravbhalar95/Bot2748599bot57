import os
import logging
from flask import Flask, request
import telebot
import yt_dlp
import re
from urllib.parse import urlparse, parse_qs
from mega import Mega
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

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
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Supported domains
SUPPORTED_DOMAINS = ['youtube.com', 'youtu.be', 'instagram.com', 'x.com', 'facebook.com']

# Mega client
mega_client = None

# User sessions for login/logout
user_sessions = {}


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


# Mega login command
@bot2.message_handler(commands=['meganz'])
def handle_mega_login(message):
    try:
        args = message.text.split(maxsplit=2)
        if len(args) < 3:
            bot2.reply_to(message, "Usage: /meganz <username> <password>")
            return

        username = args[1]
        password = args[2]

        global mega_client
        mega_client = Mega().login(username, password)
        if mega_client is not None:
            bot2.reply_to(message, "Successfully logged in to Mega.nz!")
        else:
            bot2.reply_to(message, "Login failed. Mega client is None.")
    except Exception as e:
        logging.error("Login failed", exc_info=True)
        bot2.reply_to(message, f"Login failed: {str(e)}")


# Download and upload to Mega.nz
@bot2.message_handler(commands=['mega'])
def handle_mega(message):
    try:
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            bot2.reply_to(message, "Usage: /mega <URL>")
            return

        url = args[1]
        handle_download_and_upload(message, url, upload_to_mega_flag=True)
    except Exception as e:
        bot2.reply_to(message, f"An error occurred: {str(e)}")


# Direct download without Mega.nz
@bot2.message_handler(func=lambda message: True, content_types=['text'])
def handle_direct_download(message):
    url = message.text.strip()
    if is_valid_url(url):
        handle_download_and_upload(message, url, upload_to_mega_flag=False)
    else:
        bot2.reply_to(message, "Please provide a valid URL to download the video.")


# /start command with Login and Logout buttons
@bot2.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.chat.id
    is_logged_in = user_id in user_sessions

    # Inline keyboard for Login and Logout
    keyboard = InlineKeyboardMarkup()
    if is_logged_in:
        keyboard.add(InlineKeyboardButton("Logout", callback_data="logout"))
    else:
        login_url = f"https://your-auth-service.com/login?user_id={user_id}"
        keyboard.add(InlineKeyboardButton("Login", url=login_url))

    bot2.reply_to(
        message,
        f"Hello, {message.from_user.first_name}!\n\n"
        "I am your Media Downloader bot. Here's what I can do:\n\n"
        "✅ Download videos from supported platforms.\n"
        "✅ Upload videos to Mega.nz.\n\n"
        "Commands:\n"
        "• /meganz <username> <password> - Login to Mega.nz.\n"
        "• /mega <URL> - Download and upload to Mega.nz.\n"
        "• Paste a valid URL to download directly.\n\n"
        f"{'You are logged in!' if is_logged_in else 'Please log in to continue.'}",
        reply_markup=keyboard
    )


# Callback query handler for Logout
@bot2.callback_query_handler(func=lambda call: call.data == "logout")
def handle_logout(call):
    user_id = call.message.chat.id
    if user_id in user_sessions:
        del user_sessions[user_id]  # Remove user session
        bot2.answer_callback_query(call.id, "You have been logged out.")
        bot2.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="You have successfully logged out.\n\nClick /start to log in again."
        )
    else:
        bot2.answer_callback_query(call.id, "You are not logged in.")


# Endpoint to handle login redirection
@app.route('/login_redirect', methods=['GET'])
def login_redirect():
    user_id = request.args.get('user_id')
    if user_id:
        user_sessions[int(user_id)] = True  # Mark user as logged in
        bot2.send_message(
            int(user_id),
            "You have successfully logged in! 🎉\n\nClick /start to begin using the bot."
        )
        return "Login successful! You can close this page.", 200
    return "Invalid login attempt.", 400


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