# Use a base image with Python and add ffmpeg installation
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Install ffmpeg and move it to /bin
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    mv /usr/bin/ffmpeg /bin/ && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application files
COPY . .

# Expose the port (if applicable)
EXPOSE 8080

# Command to run the application
CMD ["python", "app.py"]