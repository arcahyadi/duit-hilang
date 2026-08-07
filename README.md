# Financial Tracker

Aplikasi pencatat keuangan pribadi berbasis web untuk 2 user (admin + 1 user), data terpisah per user.

## Stack

FastAPI + PostgreSQL + Jinja2/Bootstrap/Chart.js, deploy Docker Compose + Caddy.

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

## Deploy (VPS)

```bash
cp .env.example .env   # isi semua nilai
docker compose up -d --build
```

- Caddy otomatis ambil sertifikat HTTPS untuk `DOMAIN` (arahkan DNS A ke VPS dulu)
- Migrasi DB jalan otomatis saat container start
- Backup: jalankan `scripts/backup.sh` via cron di host, atau di dalam container `db`

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
