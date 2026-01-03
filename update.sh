#!/bin/bash
set -euo pipefail

# Pfad zum Projektordner (ANPASSEN!)
PROJECT_DIR="/home/raspiroman/webcam"
SERVICE_SRC="$PROJECT_DIR/systemd/webcam_ntfy.service"
SERVICE_DST="/etc/systemd/system/webcam_ntfy.service"

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
sudo systemctl status webcam_ntfy.service --no-pager
