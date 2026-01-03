#!/bin/bash
set -euo pipefail

sudo cp cam.conf /etc/nginx/sites-available/cam.conf
sudo ln -sf /etc/nginx/sites-available/cam.conf /etc/nginx/sites-enabled/cam.conf
sudo nginx -t
sudo systemctl reload nginx