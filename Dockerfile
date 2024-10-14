# Use the official Python image
FROM python:3.9-slim

# Install ffmpeg
RUN apt-get update && apt-get install -y ffmpeg && apt-get clean

# Set the working directory
WORKDIR /app

# Copy the requirements file and install dependencies
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY app.py app.py
COPY cookies.txt cookies.txt  # Make sure you have this file in the same directory

# Ensure the output directory exists
RUN mkdir -p /app/downloads

# Set the command to run your app
CMD ["python", "app.py"]