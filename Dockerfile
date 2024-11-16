# Use a base Python image
FROM python:3.10-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Install system dependencies and ensure ffmpeg is correctly linked
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    ln -sf /bin/ffmpeg /usr/bin/ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /app

# Copy the application code
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose port 8080
EXPOSE 8080

# Command to run the Flask application
CMD python app.py