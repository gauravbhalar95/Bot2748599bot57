import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp
import nest_asyncio
from urllib.parse import urlparse
from mega import Mega
import re

# Enable logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Apply the patch for nested event loops
nest_asyncio.apply()

# Environment variables
API_TOKEN = os.getenv('BOT_TOKEN')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')
PORT = int(os.getenv('PORT', 8080))  # Default to 8080 if not set

COOKIES_FILE = 'cookies.txt'
OUTPUT_DIR = 'downloads/'

# Ensure directories and files
os.makedirs(OUTPUT_DIR, exist_ok=True)
if not os.path.exists(COOKIES_FILE):
    logger.warning(f"{COOKIES_FILE} not found. Some videos may require authentication.")

# Initialize Mega client
mega_client = None

# Telegram bot application
app = ApplicationBuilder().token(API_TOKEN).build()

# Utility: Sanitize filenames
def sanitize_filename(filename, max_length=250):
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)
    return filename.strip()[:max_length]

# Utility: Validate URL
def is_valid_url(url):
    supported_domains = ['youtube.com', 'youtu.be', 'instagram.com', 'x.com', 'facebook.com']
    try:
        result = urlparse(url)
        return result.scheme in ['http', 'https'] and any(domain in result.netloc for domain in supported_domains)
    except ValueError:
        return False

# Utility: Download media
def download_media(url, start_time=None, end_time=None):
    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'outtmpl': f'{OUTPUT_DIR}{sanitize_filename("%(title)s")}.%(ext)s',
        'cookiefile': COOKIES_FILE if os.path.exists(COOKIES_FILE) else None,
        'postprocessors': [{'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'}],
        'socket_timeout': 10,
        'retries': 5,
    }
    if start_time and end_time:
        ydl_opts['postprocessor_args'] = ['-ss', start_time, '-to', end_time]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            return ydl.prepare_filename(info_dict)
    except Exception as e:
        logger.error(f"Error downloading media: {e}")
        return None

# Utility: Upload to Mega.nz
def upload_to_mega(file_path):
    if mega_client is None:
        raise Exception("Mega.nz client not logged in. Use /meganz to log in.")
    try:
        file = mega_client.upload(file_path)
        return mega_client.get_upload_link(file)
    except Exception as e:
        logger.error(f"Error uploading to Mega: {e}")
        return None

# Command: /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome! Send me a video link to download.")

# Command: /meganz
async def meganz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global mega_client
    args = update.message.text.split()
    try:
        if len(args) == 1:
            mega_client = Mega().login()
            await update.message.reply_text("Logged in to Mega.nz anonymously!")
        elif len(args) == 3:
            email, password = args[1], args[2]
            mega_client = Mega().login(email, password)
            await update.message.reply_text("Successfully logged in to Mega.nz!")
        else:
            await update.message.reply_text("Usage: /meganz <username> <password> or /meganz for anonymous login")
    except Exception as e:
        await update.message.reply_text(f"Login failed: {e}")

# Handle URLs for downloading and optionally uploading to Mega.nz
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if not is_valid_url(url):
        await update.message.reply_text("Invalid or unsupported URL. Supported platforms: YouTube, Instagram, Twitter, Facebook.")
        return

    await update.message.reply_text("Downloading video...")
    video_path = download_media(url)

    if video_path is None:
        await update.message.reply_text("Error: Video download failed.")
        return

    if mega_client:
        await update.message.reply_text("Uploading video to Mega.nz...")
        mega_link = upload_to_mega(video_path)
        if mega_link:
            await update.message.reply_text(f"Video uploaded to Mega.nz: {mega_link}")
        else:
            await update.message.reply_text("Error uploading to Mega.nz.")
    else:
        with open(video_path, 'rb') as video:
            await update.message.reply_video(video)

    os.remove(video_path)

# Add handlers
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("meganz", meganz))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# Run the bot with webhook
if __name__ == '__main__':
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=WEBHOOK_URL.split('/')[-1],
        webhook_url=WEBHOOK_URL
    )