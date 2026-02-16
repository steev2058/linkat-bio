# Hardening Checklist - Linkat

## Secrets
- [ ] Keep `.env` out of git
- [ ] Rotate admin password and bot token regularly
- [ ] Restrict file permissions: `chmod 600 .env`

## App Security
- [ ] Only allow `http/https` links
- [ ] Block `javascript:` and `data:` schemes
- [ ] Sanitize user text input (name/bio/offers)
- [ ] Rate-limit `/u/*` and `/r/*` endpoints
- [ ] Validate voucher input and admin form values

## Nginx / TLS
- [ ] Force HTTPS via certbot redirect
- [ ] Keep nginx updated
- [ ] Add security headers (optional hardening)

## Server Ops
- [ ] Daily DB backup (`linkat.db`)
- [ ] Log rotation for systemd/nginx
- [ ] Monitoring: uptime + health check alerts
- [ ] Optional: fail2ban for ssh/nginx

## Backups
- [ ] Backup `/opt/pety-bio/linkat.db`
- [ ] Backup `/var/www/linkat/uploads`
- [ ] Keep at least 7 daily snapshots
