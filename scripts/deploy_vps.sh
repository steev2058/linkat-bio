#!/usr/bin/env bash
set -euo pipefail

REPO_URL=${REPO_URL:-https://github.com/steev2058/linkat-bio.git}
APP_DIR=${APP_DIR:-/opt/pety-bio}
DOMAIN=${DOMAIN:-pety.company}
PORT=${PORT:-8090}

sudo mkdir -p "$APP_DIR"
if [ ! -d "$APP_DIR/.git" ]; then
  sudo git clone "$REPO_URL" "$APP_DIR"
fi

cd "$APP_DIR"
sudo git pull origin main

sudo python3 -m venv .venv
sudo .venv/bin/pip install -r requirements.txt

sudo mkdir -p /var/www/linkat/uploads
sudo chown -R root:root /var/www/linkat

if [ ! -f .env ]; then
  sudo cp .env.example .env
  echo "Please edit $APP_DIR/.env before starting services"
fi

sudo tee /etc/systemd/system/linkat-web.service > /dev/null <<EOF
[Unit]
Description=Linkat FastAPI Web
After=network.target

[Service]
User=root
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port $PORT
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/linkat-bot.service > /dev/null <<EOF
[Unit]
Description=Linkat Telegram Bot
After=network.target

[Service]
User=root
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/.venv/bin/python -m bot.main
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/nginx/sites-available/$DOMAIN > /dev/null <<EOF
server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN;

    location /static/ {
        alias $APP_DIR/static/;
        expires 7d;
    }

    location /uploads/ {
        alias /var/www/linkat/uploads/;
        expires 7d;
    }

    location / {
        proxy_pass http://127.0.0.1:$PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/$DOMAIN /etc/nginx/sites-enabled/$DOMAIN
if [ ! -e /usr/bin/nginx ] && [ -e /usr/sbin/nginx ]; then
  sudo ln -s /usr/sbin/nginx /usr/bin/nginx
fi

sudo systemctl daemon-reload
sudo systemctl enable --now linkat-web
sudo nginx -t
sudo systemctl reload nginx

echo "Web deployed. For bot: set TELEGRAM_BOT_TOKEN in .env then run: sudo systemctl enable --now linkat-bot"
echo "For SSL: sudo certbot --nginx -d $DOMAIN --redirect"
