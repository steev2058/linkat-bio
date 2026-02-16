# Linkat 🔗

Arabic-first Telegram bot + FastAPI web app for link-in-bio pages.

## Product
- Public page: `https://pety.company/u/<slug>`
- Redirect tracker: `https://pety.company/r/<link_id>`
- Admin panel: `https://pety.company/admin` (HTTP Basic)
- Health: `GET /api/health -> {"status":"ok"}`

## Stack
- Bot: aiogram (FSM)
- Backend: FastAPI + Uvicorn
- Templates: Jinja2
- DB: SQLite (migration-ready for Postgres later)

## One-command local run (Replit-friendly)
```bash
make install && make dev
```

## Environment
Copy `.env.example` to `.env` and update:
- `TELEGRAM_BOT_TOKEN`
- `ADMIN_USERNAME`, `ADMIN_PASSWORD`
- `BASE_URL` (for production: `https://pety.company`)

## Telegram commands
- `/start` welcome
- `/create` wizard (name, bio, avatar optional, links, offer)
- `/edit` field edits
- `/links` add/remove/reorder
- `/publish` publish page
- `/stats` analytics summary
- `/plan` current plan + payment methods text
- `/redeem <CODE>` redeem voucher
- `/post` social text (MVP fallback)
- `/bio` 5 professional bio options
- `/lang` ar/en

## Plans
- FREE: 3 links, watermark
- PRO_1: unlimited links, no watermark, reorder, custom theme
- PRO_3: PRO_1 + featured video + advanced analytics basis

## Admin panel
- Create voucher codes: plan type + duration (30/90/365)
- Disable voucher
- List users/pages
- Stats overview (views/clicks)

## Deployment (Hostinger Ubuntu + Nginx + SSL + systemd)

### 1) Clone and setup
```bash
cd /opt
git clone https://github.com/steev2058/linkat-bio.git
cd linkat-bio
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env
```

### 2) systemd services
Create `/etc/systemd/system/linkat-web.service`:
```ini
[Unit]
Description=Linkat FastAPI
After=network.target

[Service]
User=root
WorkingDirectory=/opt/linkat-bio
EnvironmentFile=/opt/linkat-bio/.env
ExecStart=/opt/linkat-bio/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8090
Restart=always

[Install]
WantedBy=multi-user.target
```

Create `/etc/systemd/system/linkat-bot.service`:
```ini
[Unit]
Description=Linkat Telegram Bot
After=network.target

[Service]
User=root
WorkingDirectory=/opt/linkat-bio
EnvironmentFile=/opt/linkat-bio/.env
ExecStart=/opt/linkat-bio/.venv/bin/python -m bot.main
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now linkat-web linkat-bot
```

### 3) Nginx vhost (`/etc/nginx/sites-available/pety.company`)
```nginx
server {
    server_name pety.company;

    location / {
        proxy_pass http://127.0.0.1:8090;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable and reload:
```bash
sudo ln -s /etc/nginx/sites-available/pety.company /etc/nginx/sites-enabled/pety.company
sudo nginx -t && sudo systemctl reload nginx
```

### 4) SSL with certbot
```bash
sudo apt-get update
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d pety.company
```

## Migration note (SQLite -> Postgres)
Schema already normalized (`users`, `pages`, `links`, `vouchers`, `analytics_events`).
For scale, swap sqlite access layer with SQLAlchemy and Postgres DSN.
