# VPS Deploy (Hostinger Ubuntu) - Linkat

## 1) Install prerequisites
```bash
cd /opt
git clone https://github.com/steev2058/linkat-bio.git
cd linkat-bio
bash scripts/install_vps.sh
```

## 2) Deploy app to `/opt/pety-bio`
```bash
cd /opt/linkat-bio
REPO_URL=https://github.com/steev2058/linkat-bio.git APP_DIR=/opt/pety-bio DOMAIN=pety.company bash scripts/deploy_vps.sh
```

## 3) Configure environment
```bash
sudo nano /opt/pety-bio/.env
```
Set required vars:
- `APP_ENV=prod`
- `BASE_URL=https://pety.company`
- `DB_PATH=/opt/pety-bio/linkat.db`
- `UPLOAD_DIR=/var/www/linkat/uploads`
- `ADMIN_USERNAME=...`
- `ADMIN_PASSWORD=...`
- `TELEGRAM_BOT_TOKEN=...`
- `BOT_USERNAME=YourBotUsername`
- `OPENAI_API_KEY=` (optional)

## 4) Start services
```bash
sudo systemctl restart linkat-web
sudo systemctl enable --now linkat-bot
sudo systemctl status linkat-web --no-pager
sudo systemctl status linkat-bot --no-pager
```

## 5) SSL
Make sure DNS `A` record for `pety.company` points to VPS IP, then:
```bash
sudo certbot --nginx -d pety.company --redirect
```

## 6) Verify
```bash
curl -sS https://pety.company/api/health
# expected: {"status":"ok"}
```

## Notes
- Static files served at `/static/`
- Uploads served at `/uploads/` from `/var/www/linkat/uploads`
