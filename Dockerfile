# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . .

# Install dependencies from requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Install necessary tools and download ffmpeg to /bin
RUN apt-get update && apt-get install -y wget \
    && wget https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-i686-static.tar.xz \
    && tar -xJf ffmpeg-release-i686-static.tar.xz \
    && mv ffmpeg-*/ffmpeg /bin/ffmpeg \
    && mv ffmpeg-*/ffprobe /bin/ffprobe \
    && chmod +x /bin/ffmpeg /bin/ffprobe \
    && rm -rf ffmpeg-* ffmpeg-release-i686-static.tar.xz \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Expose port 8080 for the Flask app
EXPOSE 8080

# Run app.py when the container launches
CMD python app.py