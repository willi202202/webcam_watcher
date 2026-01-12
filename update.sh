#!/bin/bash
set -euo pipefail

PROJECT_DIR="/home/raspiroman/project/webcam_watcher"
SERVICE_SRC="$PROJECT_DIR/systemd/webcam_control_app.service"
SERVICE_DST="/etc/systemd/system/webcam_control_app.service"

HTML_SRC="$PROJECT_DIR/html/webcam_api.html"
HTML_DIR="/var/www/webcam"
HTML_DST="$HTML_DIR/webcam_api.html"

LOG_ROOT="/var/www/log"
WEBCAM_LINK="$LOG_ROOT/webcam"
WEBCAM_SRC="/srv/webcam/upload"

echo "Starting update process..."
cd "$PROJECT_DIR"

echo "Pulling latest changes from Git repository..."
git pull origin main

echo "Making webcam_control_app.py executable..."
chmod +x "$PROJECT_DIR/webcam_control_app.py"

echo "Updating webcam_control_app.service..."
sudo cp "$SERVICE_SRC" "$SERVICE_DST"

echo "Reloading systemd daemon..."
sudo systemctl daemon-reload

echo "Enabling and restarting webcam_control_app.service..."
#sudo systemctl disable --now webcam_control_app.service
sudo systemctl enable --now webcam_control_app.service

echo "Status of webcam_control_app.service:"
sudo systemctl status webcam_control_app.service --no-pager || true

echo "Ensuring HTML directory exists..."
sudo mkdir -p "$HTML_DIR"

echo "Updating webcam_images.html..."
sudo cp "$HTML_SRC" "$HTML_DST"

echo "Fixing ownership and permissions for /var/www/webcam..."
sudo chown -R raspiroman:www-data "$HTML_DIR"
sudo chmod 775 "$HTML_DIR"

echo "Ensuring webcam log root directory exists..."
sudo mkdir -p "$LOG_ROOT"
sudo chown www-data:www-data "$LOG_ROOT"

echo "Resetting symbolic link for webcam directory..."
if [ -L "$WEBCAM_LINK" ]; then
    sudo rm "$WEBCAM_LINK"
fi
sudo ln -s "$WEBCAM_SRC" "$WEBCAM_LINK"
sudo chown -h www-data:www-data "$WEBCAM_LINK"

echo "Testing nginx config..."
sudo nginx -t

echo "Reloading nginx..."
sudo systemctl reload nginx

echo "Update completed."
