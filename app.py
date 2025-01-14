import os
import logging
from flask import Flask, request
import telebot
import requests
from urllib.parse import urlparse

# Load environment variables
API_TOKEN_2 = os.getenv('API_TOKEN_2')
CHANNEL_ID = os.getenv('CHANNEL_ID')  # Example: '@YourChannel'
KOYEB_URL = os.getenv('KOYEB_URL')  # Koyeb URL for webhook
HIKER_API_TOKEN = os.getenv('HIKER_API_TOKEN')  # Hiker API token

# Initialize bot
bot2 = telebot.TeleBot(API_TOKEN_2, parse_mode='HTML')

# Logging configuration
logging.basicConfig(level=logging.DEBUG)

# Hiker API base URL
HIKER_API_URL = "https://api.hikerapi.com/v1/user/by/username"

def fetch_user_info(username):
    """
    Fetches user information from the Hiker API using the username.

    Args:
        username (str): The username to fetch information for.

    Returns:
        dict: The user details if found, otherwise an error message.
    """
    try:
        # API endpoint and headers
        url = f"{HIKER_API_URL}?username={username}"
        headers = {
            "Authorization": f"Bearer {HIKER_API_TOKEN}"
        }

        # Make the API request
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            # Parse and return the response JSON
            return response.json()
        else:
            # Handle errors
            return {"error": f"API returned status code {response.status_code}", "details": response.text}

    except Exception as e:
        # Handle unexpected errors
        return {"error": "An exception occurred", "details": str(e)}

# Handle the /user command to fetch user details
@bot2.message_handler(commands=['user'])
def handle_user_command(message):
    try:
        # Extract the username from the command
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            bot2.reply_to(message, "Please provide a username. Usage: /user <username>")
            return

        username = args[1].strip()
        bot2.reply_to(message, f"Fetching information for username: {username}...")

        # Fetch user information from Hiker API
        user_info = fetch_user_info(username)

        if 'error' in user_info:
            # Handle API errors
            bot2.reply_to(message, f"Error: {user_info['error']}\nDetails: {user_info.get('details', '')}")
        else:
            # Format and send user details
            response_message = (
                f"User Information:\n"
                f"Name: {user_info.get('name', 'N/A')}\n"
                f"Username: {user_info.get('username', 'N/A')}\n"
                f"Followers: {user_info.get('followers', 'N/A')}\n"
                f"Posts: {user_info.get('posts', 'N/A')}"
            )
            bot2.reply_to(message, response_message)

    except Exception as e:
        logging.error("Error handling /user command", exc_info=True)
        bot2.reply_to(message, f"An error occurred: {str(e)}")

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