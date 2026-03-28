#!/usr/bin/env bash
# Exit on error
set -o errexit

echo "Installing dependencies..."
pip install -r requirements.txt
echo "Force-upgrading yt-dlp to latest GitHub Master for BotGuard patches..."
pip install -U https://github.com/yt-dlp/yt-dlp/archive/master.tar.gz
echo "Installing ffmpeg..."
# yt-dlp will look for ffmpeg in PATH
FFMPEG_DIR=/opt/render/project/src/ffmpeg
if [ ! -f "$FFMPEG_DIR/ffmpeg" ]; then
    mkdir -p $FFMPEG_DIR
    cd $FFMPEG_DIR
    echo "Downloading ffmpeg Linux static build..."
    curl -L -q https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz -o ffmpeg.tar.xz
    tar -xf ffmpeg.tar.xz --strip-components=1
    rm ffmpeg.tar.xz
    echo "ffmpeg installed successfully"
else
    echo "ffmpeg is already installed"
fi
