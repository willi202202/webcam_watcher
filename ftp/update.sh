#!/bin/bash
set -euo pipefail

echo "Updating vsftpd configuration..."
sudo cp vsftpd.conf /etc/vsftpd.conf

echo "Restarting vsftpd service..."
sudo systemctl enable vsftpd
sudo systemctl restart vsftpd

echo "Status of vsftpd service:"
sudo systemctl status vsftpd --no-pager

echo "Setting up webcam group and permissions..."
sudo groupadd webcam
sudo usermod -a -G webcam ftpuser
sudo usermod -a -G webcam raspiroman
sudo usermod -a -G webcam www-data
sudo chgrp -R webcam /srv/webcam/upload
sudo chmod -R 2775 /srv/webcam/upload
