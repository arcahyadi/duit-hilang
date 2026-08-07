# Financial Tracker

Aplikasi pencatat keuangan pribadi berbasis web untuk 2 user (admin + 1 user), data terpisah per user.

## Stack

FastAPI + PostgreSQL + Jinja2/Bootstrap/Chart.js, deploy Docker Compose + Cloudflare Tunnel (cloudflared di host).

## Fitur

- Auth: login password (Argon2), 2FA TOTP opsional, passkey (WebAuthn), rate limiting
- Transaksi: date, type (income/expense), amount, category, account, note
- Dashboard, budget per kategori + progress, laporan per bulan
- Export CSV
- API read-only dengan API key (hanya admin yang bisa buat), docs di `/docs`
- Admin: kelola user, kelola API key
- Backup: `scripts/backup.sh` (pg_dump + scp opsional)

## Development (lokal)

```bash
# Python 3.13 wajib
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/alembic upgrade head          # jalankan migration
.venv/bin/uvicorn app.main:app --reload
# buka http://localhost:8000, admin login dari ADMIN_EMAIL/ADMIN_PASSWORD (.env)
```

Self-check:

```bash
.venv/bin/python tests/self_check.py
```

## Deploy (VPS + Cloudflare Tunnel + Portainer)

Akses publik lewat Cloudflare Tunnel; cloudflared jalan di host VPS, app tidak perlu port publik.

```bash
# 1. Siapkan .env di VPS (dari .env.example)
cp .env.example .env   # isi DOMAIN, SECRET_KEY, DB_PASSWORD, ADMIN_*
```

```bash
# 2. Build image + seed data volume sekali (di VPS)
docker compose up -d --build   # jalankan sekali: buat volume + migration
docker compose stop            # stop; volume financial-tracker_pgdata tetap ada
```

```bash
# 3. Buat stack di Portainer (UI atau API), isi dari docker-compose.portainer.yml
#    - Set env stack: DB_PASSWORD, SECRET_KEY, DOMAIN, ADMIN_EMAIL, ADMIN_PASSWORD
#    - Volume pgdata external: name financial-tracker_pgdata
#    - Tidak bind port; akses via cloudflared
```

```bash
# 4. Pasang cloudflared di host (bukan di compose)
cloudflared tunnel login                          # pilih domain di dashboard
cloudflared tunnel create finance                 # catat Tunnel ID
cloudflared tunnel route dns finance <DOMAIN>     # buat DNS CNAME
```

```bash
# 5. Buat /etc/cloudflared/config.yml
tunnel: <Tunnel-ID>
credentials-file: /root/.cloudflared/<Tunnel-ID>.json

ingress:
  - hostname: <DOMAIN>
    service: http://localhost:8000
  - service: http_status:404
```

```bash
# 6. Jalankan sebagai service
cloudflared service install
systemctl start cloudflared
# buka https://<DOMAIN>
```

Catatan penting dari pengalaman deploy:
- `config.py` memakai `extra="ignore"` supaya env Docker (`DB_PASSWORD`, `DOMAIN`, dll) tidak menolak Settings
- Jangan pernah dua postgres memakai volume yang sama; stack Portainer memakai volume external `financial-tracker_pgdata`
- Update aplikasi: build image baru (langkah 2), lalu update stack di Portainer (ganti `image: financial-tracker-app:latest` tetap, container recreate)

## API

Autentikasi: header `X-API-Key: ft_...`

```
GET /api/v1/transactions?from=2026-08-01&to=2026-08-31&type=expense
GET /api/v1/transactions/{id}
GET /api/v1/summary?month=2026-08
GET /api/v1/categories
GET /api/v1/accounts
GET /api/v1/budgets?month=2026-08
```

## Struktur

```
app/
  main.py        # entry FastAPI, CSRF, seed admin
  config.py      # settings via env
  database.py    # engine + session
  models.py      # SQLAlchemy models
  security.py    # hashing, session token, rate limit
  deps.py        # auth dependencies
  ui.py          # template helpers
  routes/        # auth, web, api, admin
  templates/     # Jinja2
migrations/      # Alembic
tests/           # self_check.py
scripts/         # backup.sh
```
