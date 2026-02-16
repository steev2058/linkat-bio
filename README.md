# Linkat 🔗

Telegram bot + FastAPI app (Arabic-first) for link-in-bio pages, Syria-first.

## Features
- Public page: `https://pety.company/u/<slug>`
- Redirect tracking: `/r/<link_id>`
- Telegram wizard to create/edit/publish page
- Plans: FREE / PRO_1 / PRO_3 via voucher codes
- Analytics: views/clicks + top links + 7-day stats
- Admin panel: `/admin` (basic auth via env)
- Marketing website pages:
  - `/` Home
  - `/pricing`
  - `/examples`
  - `/faq`
  - `/contact`

## Required security rules implemented
- URL validation: only `http/https`
- Block `javascript:` and `data:`
- Input sanitization for text fields
- Safe redirect validation in `/r/*`
- Basic in-memory rate limiting on `/u/*` and `/r/*`
- Upload path by env:
  - Dev/Replit: `./data/uploads`
  - VPS: `/var/www/linkat/uploads`

## One-command local run (Replit-friendly)
```bash
make install && make dev
```

## Environment
Copy `.env.example` to `.env` and set:
- `TELEGRAM_BOT_TOKEN`
- `BOT_USERNAME`
- `ADMIN_USERNAME`, `ADMIN_PASSWORD`
- `BASE_URL`
- `DB_PATH`
- `UPLOAD_DIR`
- `OPENAI_API_KEY` (optional)

## Commands (bot)
`/start /create /edit /links /publish /stats /plan /redeem /post /bio /lang`

## Tests
```bash
pytest -q
```

## Seed sample data
```bash
python -m scripts.seed_sample
```

## VPS deploy docs
- `docs/VPS_DEPLOY.md`
- `docs/HARDENING_CHECKLIST.md`

## Quick deployment script
```bash
bash scripts/install_vps.sh
REPO_URL=https://github.com/steev2058/linkat-bio.git APP_DIR=/opt/pety-bio DOMAIN=pety.company bash scripts/deploy_vps.sh
```
