# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set environment variables to configure Python and application paths
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OUTPUT_DIR=/app/downloads

# Set the working directory in the container
WORKDIR /app

# Install system dependencies required for media processing
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies from the requirements file
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
COPY . /app/

# Create the download directory for storing media files
RUN mkdir -p ${OUTPUT_DIR}

# Expose the port on which the Flask server will run
EXPOSE 8080

# Command to run your Flask application
CMD python app.py