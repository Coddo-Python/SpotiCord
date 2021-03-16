FROM python:3.9-slim

# Update packages list
RUN apt update -y

# Install deps
RUN apt install wget xz-utils -y

# Change workdir
WORKDIR /app

# Download ffmpeg
RUN wget https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2021-08-02-14-11/ffmpeg-n4.4-79-gde1132a891-linux64-gpl-4.4.tar.xz

# Download opus
RUN apt install opus-tools -y

# Unpack ffmpeg folder
RUN tar xf ./ffmpeg-n4.4-79-gde1132a891-linux64-gpl-4.4.tar.xz

# Add to bin folder
RUN mv ./ffmpeg-n4.4-79-gde1132a891-linux64-gpl-4.4/bin/ffmpeg /usr/local/bin

# Cleanup
RUN rm -rf ./ffmpeg-n4.4-79-gde1132a891-linux64-gpl-4.4
RUN rm ./ffmpeg-n4.4-79-gde1132a891-linux64-gpl-4.4.tar.xz

# Install requirements
COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt

# Start bot
COPY src .
CMD ["python", "main.py"]