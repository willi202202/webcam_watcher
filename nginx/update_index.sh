#!/bin/bash
set -euo pipefail

sudo cp index.conf /etc/nginx/sites-available/index.conf
sudo ln -sf /etc/nginx/sites-available/index.conf /etc/nginx/sites-enabled/index.conf
sudo nginx -t
sudo systemctl reload nginx