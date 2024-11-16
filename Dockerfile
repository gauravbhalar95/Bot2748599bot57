# Start with a base image
FROM ubuntu:latest

# Install ffmpeg and move it to /bin if necessary
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    if [ ! -f /bin/ffmpeg ]; then mv /usr/bin/ffmpeg /bin/; fi && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Verify ffmpeg installation (optional)
RUN /bin/ffmpeg -version

# Set the working directory
WORKDIR /app

# Copy your application code (replace this with your actual files)
COPY . /app

# Install dependencies (modify as needed based on your application)
# RUN pip install -r requirements.txt  # Example for Python projects

# Specify the entry point (modify this based on your app)
# ENTRYPOINT ["python", "app.py"]      # Example for Python projects