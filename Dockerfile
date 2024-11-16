# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Install ffmpeg for yt-dlp to merge video and audio streams
RUN apt-get update && apt-get install -y ffmpeg

# Expose port 8080 for the Flask app
EXPOSE 8080

# Run app.py when the container launches
CMD python app.py