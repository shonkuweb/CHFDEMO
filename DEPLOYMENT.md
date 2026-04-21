# CHF Docker Deployment (VPS)

## 1) Clone and configure

```bash
git clone <your-repo-url> chf-app
cd chf-app
cp .env.example .env   # or create .env manually
```

Set production values in `.env`:
- `JWT_SECRET` (strong random secret)
- `TURNSTILE_SECRET`
- `R2_ACCOUNT_ID`
- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`
- `R2_BUCKET_NAME`
- `R2_PUBLIC_URL`
- `CF_ZONE_ID` (Cloudflare zone ID for your domain)
- `CF_API_TOKEN` (token with `Zone.Cache Purge:Edit`)

## 2) Build and run

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f chf-web
```

The app is published internally on `127.0.0.1:8000` for reverse-proxy use.

## 3) Nginx reverse proxy

Use `nginx_template.conf` and replace domain values:
- `yourdomain.com`
- SSL certificate paths

Then:

```bash
sudo ln -s /var/www/chf_app/nginx_template.conf /etc/nginx/sites-available/chf
sudo ln -s /etc/nginx/sites-available/chf /etc/nginx/sites-enabled/chf
sudo nginx -t
sudo systemctl reload nginx
```

## 4) Zero-friction git deploy updates

When you push new code:

```bash
cd /var/www/chf_app
git pull origin main
docker compose up -d --build
```

## 5) Data persistence

- SQLite DB and uploads are stored in Docker volume `chf_data`.
- First run seeds `/app/data/chf_archive.db` from repo snapshot if missing.
- Container recreates do not wipe data.

## 6) Cloudflare production sync

- API responses are sent with `no-store` cache headers.
- Admin publish actions trigger automatic Cloudflare cache purge (when `CF_ZONE_ID` + `CF_API_TOKEN` are set).
- This keeps CDN edge content in sync with admin updates.

