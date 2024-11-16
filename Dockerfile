# Use the official Python 3.9 slim image as a base image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file
COPY requirements.txt .

# Install dependencies and move ffmpeg to /bin
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    mv /usr/bin/ffmpeg /bin/ && \
    pip install --no-cache-dir -r requirements.txt && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy the rest of the application code
COPY . .

# Expose the port the app runs on (if applicable, you can change the port number)
EXPOSE 8000

# Command to run the application
CMD python app.py