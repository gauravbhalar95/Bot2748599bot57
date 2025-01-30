import os
import logging
import psutil
import yt_dlp
import ffmpeg
from flask import Flask, request
import telebot
from urllib.parse import urlparse
from threading import Thread
import queue
import re
import gc

# Environment variables
API_TOKEN = os.getenv('BOT_TOKEN')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')
PORT = int(os.getenv('PORT', 8080))

# Initialize bot
bot = telebot.TeleBot(API_TOKEN, parse_mode='Markdown')

# Directories
output_dir = 'downloads/'
cookies_file = 'cookies.txt'

# Ensure downloads directory exists
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# Logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Supported domains
SUPPORTED_DOMAINS = ['youtube.com', 'youtu.be', 'instagram.com', 'x.com',
                     'facebook.com', 'xvideos.com', 'xnxx.com', 'xhamster.com', 'pornhub.com']

# Task queue for threading
task_queue = queue.Queue()


# Check if URL is valid
def is_valid_url(url):
    try:
        result = urlparse(url)
        return result.scheme in ['http', 'https'] and any(domain in result.netloc for domain in SUPPORTED_DOMAINS)
    except ValueError:
        return False


# Extract timestamps from message
def extract_timestamps(text):
    match = re.search(r'(\d{1,2}:\d{2})\s+(\d{1,2}:\d{2})$', text)
    if match:
        return match.group(1), match.group(2)
    return None, None


# Get video metadata (thumbnail, title, duration)
def get_video_info(url):
    ydl_opts = {'quiet': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                "title": info.get('title', 'Unknown Title'),
                "duration": info.get('duration', 0),
                "thumbnail": info.get('thumbnail', None)
            }
    except Exception as e:
        logger.error(f"Error fetching video info: {e}")
        return None


# Download and trim video
def download_and_trim_video(url, start_time, end_time):
    output_filename = "video.mp4"
    
    # Download video using yt-dlp
    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'outtmpl': 'video.%(ext)s',
        'retries': 5,
        'cookiefile': cookies_file,
        'postprocessors': [{'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'}],
        'socket_timeout': 10,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            video_filename = ydl.prepare_filename(info_dict)

        # If timestamps are provided, trim the video using FFmpeg
        if start_time and end_time:
            trimmed_filename = "trimmed_video.mp4"
            (
                ffmpeg
                .input(video_filename, ss=start_time, to=end_time)
                .output(trimmed_filename, vcodec="libx264", acodec="aac", strict="experimental")
                .run(overwrite_output=True)
            )
            os.remove(video_filename)  # Remove original video
            return trimmed_filename
        return video_filename

    except Exception as e:
        logger.error(f"Error downloading/trimming video: {e}")
        return None


# Process video request
def handle_request(url, message, start_time, end_time):
    video_info = get_video_info(url)
    
    if video_info and video_info["thumbnail"]:
        bot.send_photo(
            message.chat.id, 
            video_info["thumbnail"], 
            caption=f"🎬 **{video_info['title']}**\n⏳ Duration: {video_info['duration']} sec\n\n"
                    f"🔄 **Processing your request...**"
        )
    else:
        bot.reply_to(message, "⏳ **Processing your request...** Please wait.")

    video_file = download_and_trim_video(url, start_time, end_time)
    
    if video_file:
        with open(video_file, 'rb') as video:
            bot.send_video(message.chat.id, video)

        os.remove(video_file)  # Delete file after sending
        gc.collect()
    else:
        bot.reply_to(message, "⚠️ **Failed to process video.** Please try again later.")


# Worker thread for handling tasks
def worker():
    while True:
        task = task_queue.get()
        if task is None:
            break
        url, message, start_time, end_time = task
        handle_request(url, message, start_time, end_time)
        task_queue.task_done()


# Start worker threads
for _ in range(4):
    Thread(target=worker, daemon=True).start()


# Command: /start
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "👋 **Welcome!**\nSend a YouTube link with timestamps to trim, or just the link to download full video.")


# Handle YouTube video download requests with trimming
@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_message(message):
    text = message.text.strip()
    
    if not is_valid_url(text):
        bot.reply_to(message, "❌ **Invalid or unsupported URL.**")
        return

    url, start_time, end_time = text, None, None

    if "youtube.com" in text or "youtu.be" in text:
        url, start_time, end_time = re.split(r'\s+', text, maxsplit=1)[0], *extract_timestamps(text)

    task_queue.put((url, message, start_time, end_time))


# Flask app for webhook
app = Flask(__name__)

@app.route('/' + API_TOKEN, methods=['POST'])
def webhook():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "OK", 200

@app.route('/')
def set_webhook():
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL + '/' + API_TOKEN, timeout=60)
    return "✅ Webhook set", 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)