FROM python:3.9-slim

# Install ffmpeg
RUN apt-get update && apt-get install -y ffmpeg

# Install necessary Python packages
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

# Copy your bot's code to the container
COPY . /app
WORKDIR /app

CMD ["python", "app.py"]
