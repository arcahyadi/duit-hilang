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

Akses publik lewat Cloudflare Tunnel; cloudflared jalan di host VPS, app bind
`127.0.0.1:8000` (localhost saja, tidak terbuka ke publik).

```bash
# 1. Siapkan .env di VPS (dari .env.example)
cp .env.example .env   # isi DOMAIN, SECRET_KEY, DB_PASSWORD, ADMIN_*, RP_ID, RP_ORIGIN
```

```bash
# 2. Build image + seed data volume sekali (di VPS)
docker compose up -d --build   # jalankan sekali: buat volume + migration
docker compose stop            # stop; volume financial-tracker_pgdata tetap ada
```

```bash
# 3. Buat stack di Portainer (UI atau API), isi dari docker-compose.portainer.yml
#    - Set env stack: DB_PASSWORD, SECRET_KEY, DOMAIN, ADMIN_EMAIL, ADMIN_PASSWORD,
#      RP_ID, RP_ORIGIN (https://<DOMAIN>), COOKIE_SECURE=true
#    - Volume pgdata external: name financial-tracker_pgdata
#    - Bind port 127.0.0.1:8000 (penting: cloudflared di host akses lewat localhost)
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
- `RP_ID`/`RP_ORIGIN` wajib diisi persis domain (dipakai WebAuthn + CSRF check). `COOKIE_SECURE=true` untuk HTTPS
- Update aplikasi: build image baru (`docker build -t financial-tracker-app:latest .`), lalu update stack di Portainer (container recreate)
- HTTP/HTTPS otomatis via `scripts/start.sh`: isi `SSL_CERTFILE` + `SSL_KEYFILE` untuk HTTPS langsung, kosongkan untuk HTTP (akses normal via Cloudflare Tunnel tetap HTTPS di edge)

## API

### Autentikasi

Semua endpoint API butuh header `X-API-Key`. Key dibuat oleh **admin** di halaman
Admin (`/admin`). Saat membuat, admin memilih scope:

| Scope | Bisa | Badge di Admin |
|---|---|---|
| Read-only (default) | Semua `GET` | `Read-only` |
| Read+Write | `GET` + `POST /api/v1/transactions` | `Read+Write` |

Key hanya ditampilkan **sekali** saat dibuat, simpan baik-baik. Di database key
disimpan hashed (SHA-256). Key bisa di-revoke kapan saja dari halaman Admin.

```
Header: X-API-Key: ft_...
```

| Kode | Arti |
|---|---|
| 401 | Key tidak ada / salah / sudah di-revoke |
| 403 | Key valid tapi read-only, tidak boleh POST |
| 422 | Body tidak valid (lihat detail error) |
| 429 | Terlalu banyak request (rate limit) |

### Base URL

- Lokal: `http://localhost:8000/api/v1`
- VPS: `https://<domain>/api/v1` (ganti `<domain>` dengan domain yang dipakai)

Docs interaktif (Swagger): buka `/docs` di browser.

---

### GET /transactions — daftar transaksi

**Query params (semua opsional):**

| Param | Contoh | Keterangan |
|---|---|---|
| `from` | `2026-08-01` | Ambil transaksi dari tanggal ini |
| `to` | `2026-08-31` | Sampai tanggal ini |
| `type` | `expense` | Filter `income` / `expense` |
| `category_id` | uuid | Filter kategori |
| `account_id` | uuid | Filter akun |

**Request:**

```bash
curl "https://<domain>/api/v1/transactions?from=2026-08-01&to=2026-08-31&type=expense" \
  -H "X-API-Key: ft_..."
```

**Response `200`:**
```json
[
  {
    "id": "d3e18e33-...",
    "date": "2026-08-07",
    "type": "expense",
    "amount": 25000.0,
    "category": "makanan ringan",
    "category_id": "4c2ec205-...",
    "account": "gopay",
    "account_id": "0d29a733-...",
    "note": "test via api"
  }
]
```

### GET /transactions/{id} — detail transaksi

```bash
curl "https://<domain>/api/v1/transactions/d3e18e33-afda-4fcd-bda9-c5e64aa7c500" \
  -H "X-API-Key: ft_..."
```

Response `200` sama dengan satu objek di atas. `{"detail": "Not found"}` kalau
tidak ada atau bukan milik pemilik key.

### POST /transactions — buat transaksi (butuh key Read+Write)

**Body JSON:**

| Field | Wajib | Tipe | Keterangan |
|---|---|---|---|
| `date` | ✅ | `YYYY-MM-DD` | Tanggal transaksi |
| `type` | ✅ | string | `income` atau `expense` |
| `amount` | ✅ | number | > 0 |
| `category` | | string | Nama kategori (autocreate, case-insensitive) |
| `category_id` | | uuid | ID kategori (alternatif dari `category`) |
| `account` | | string | Nama akun (autocreate, case-insensitive) |
| `account_id` | | uuid | ID akun (alternatif dari `account`) |
| `note` | | string | Catatan, maks 500 karakter |

**Aturan kategori/akun:**
- Kirim **nama** atau **ID** — jangan keduanya (→ 422)
- Case-insensitive: `MaKan` / `makan` → pakai `Makan` yang sudah ada di DB
  (kapital mengikuti yang tersimpan)
- Belum ada → **dibuat otomatis** dengan kapital persis kiriman
- `category_id` / `account_id` yang tidak dikenal → 422

**Request:**

```bash
curl -X POST "https://<domain>/api/v1/transactions" \
  -H "X-API-Key: ft_..." \
  -H "Content-Type: application/json" \
  -d '{
    "date": "2026-08-07",
    "type": "expense",
    "amount": 150000,
    "category": "Makan",
    "account": "GoPay",
    "note": "dari telegram"
  }'
```

**Response `201`:**
```json
{
  "id": "e84b41a2-...",
  "date": "2026-08-07",
  "type": "expense",
  "amount": 150000.0,
  "category": "Makan",
  "category_id": "27741c1b-...",
  "account": "GoPay",
  "account_id": "...",
  "note": "dari telegram"
}
```

### GET /summary — ringkasan bulan

```bash
curl "https://<domain>/api/v1/summary?month=2026-08" \
  -H "X-API-Key: ft_..."
```

**Response `200`:**
```json
{
  "month": "2026-08",
  "income": 5000000.0,
  "expense": 235000.0,
  "balance": 4765000.0
}
```
(`month` opsional, default bulan berjalan.)

### GET /categories — daftar kategori

```bash
curl "https://<domain>/api/v1/categories" -H "X-API-Key: ft_..."
```

**Response `200`:**
```json
[{"id": "27741c1b-...", "name": "Makan", "type": "expense"}]
```

### GET /accounts — daftar akun

```bash
curl "https://<domain>/api/v1/accounts" -H "X-API-Key: ft_..."
```

**Response `200`:**
```json
[{"id": "0d29a733-...", "name": "gopay"}]
```

### GET /budgets — daftar budget + pemakaian

```bash
curl "https://<domain>/api/v1/budgets?month=2026-08" -H "X-API-Key: ft_..."
```

**Response `200`:**
```json
[
  {
    "id": "...",
    "month": "2026-08",
    "category": "Makan",
    "category_id": "...",
    "limit": 1000000.0,
    "spent": 235000.0
  }
]
```

---

### Alur integrasi (contoh: Telegram → n8n)

```
User kirim pesan ke bot Telegram
        ↓
Telegram bot (webhook) menerima pesan
        ↓
n8n: Telegram Trigger → parse teks (kategori, jumlah, catatan)
        ↓
n8n: HTTP Request node
        method: POST
        URL: https://<domain>/api/v1/transactions
        Header: X-API-Key: ft_...
        Body (JSON): {"date":"2026-08-07","type":"expense","amount":150000,"category":"Makan","account":"GoPay","note":"..."}
        ↓
Response 201 → transaksi tersimpan → muncul di dashboard
```

Catatan n8n: set header `Content-Type: application/json` dan kirim body sebagai
JSON (bukan form-encoded). Error `403` berarti key-nya read-only, buat key baru
dengan toggle Write di halaman Admin.

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
