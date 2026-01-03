#!/bin/bash
set -euo pipefail

PROJECT_DIR="/home/raspiroman/project/webcam_watcher"
SERVICE_SRC="$PROJECT_DIR/systemd/webcam_ntfy.service"
SERVICE_DST="/etc/systemd/system/webcam_ntfy.service"
HTML_SRC="$PROJECT_DIR/html/webcam_images.html"
HTML_DIR="/var/www/webcam"
HTML_DST="$HTML_DIR/webcam_images.html"

LOG_ROOT="/var/www/log"
WEBCAM_LINK="$LOG_ROOT/webcam"
WEBCAM_SRC="/srv/webcam/upload"

echo "Starting update process..."
cd "$PROJECT_DIR"

echo "Pulling latest changes from Git repository..."
git pull origin main

echo "Making webcam_ntfy_watcher.py executable..."
chmod +x "$PROJECT_DIR/webcam_ntfy_watcher.py"

echo "Updating webcam_ntfy.service..."
sudo cp "$SERVICE_SRC" "$SERVICE_DST"

echo "Reloading systemd daemon..."
sudo systemctl daemon-reload

echo "Enabling and restarting webcam_ntfy.service..."
sudo systemctl enable --now webcam_ntfy.service

echo "Status of webcam_ntfy.service:"
sudo systemctl status webcam_ntfy.service --no-pager || true

echo "Ensuring HTML directory exists..."
sudo mkdir -p "$HTML_DIR"

echo "Updating webcam_images.html..."
sudo cp "$HTML_SRC" "$HTML_DST"
sudo chown www-data:www-data "$HTML_DST"

echo "Ensuring webcam log root directory exists..."
sudo mkdir -p "$LOG_ROOT"
sudo chown www-data:www-data "$LOG_ROOT"

echo "Removing existing symbolic link for webcam directory..."
if [ -L "$WEBCAM_LINK" ]; then
    sudo rm "$WEBCAM_LINK"
fi
echo "Creating symbolic link for webcam directory..."
sudo ln -s "$WEBCAM_SRC" "$WEBCAM_LINK"
sudo chown -h www-data:www-data "$WEBCAM_LINK"

echo "Reloading nginx..."
sudo nginx -t
sudo systemctl reload nginx

echo "Update completed."
