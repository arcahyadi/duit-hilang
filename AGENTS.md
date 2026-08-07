# AGENTS.md

Petunjuk untuk AI coding agent yang bekerja di repo ini.

## Project

Aplikasi pencatat keuangan pribadi berbasis web (web app) untuk 2 user:
pemilik (admin) + 1 user lain. Data setiap user terpisah total.

## Stack

- Backend: Python FastAPI, SQLAlchemy 2, Alembic migration
- Database: PostgreSQL (produksi), SQLite hanya untuk dev/self-check
- Frontend: Jinja2 templates + Bootstrap + Chart.js, tanpa framework JS
- Auth: password Argon2, session cookie HttpOnly+Secure+SameSite=Strict,
  rate limiting, 2FA TOTP opsional, passkey (WebAuthn)
- Deploy: Docker Compose di VPS + Cloudflare Tunnel (cloudflared di host, app listen localhost saja)
- Backup: cron pg_dump ke tempat terpisah
- API: read-only, autentikasi via API key (X-API-Key) yang hanya bisa
  dibuat oleh admin, docs otomatis di /docs

## Aturan umum

- Baca file ini dulu sebelum mengerjakan tugas apa pun.
- Perubahan sekecil apa pun sebaiknya di-commit, kecuali diminta lain.
- Jangan menghapus data, mengirim email, atau melakukan aksi destruktif tanpa konfirmasi.
- Jika ragu dengan maksud user, tanya dulu sebelum menebak.

## Alur kerja

1. Pahami kebutuhan dan tuliskan rencana singkat (todo list).
2. Cari kode terkait sebelum menulis kode baru.
3. Tulis kode paling sederhana yang bekerja. Hindari abstraksi yang tidak diminta.
4. Pastikan tetap ada satu check yang bisa dijalankan (test/self-check) untuk logika non-trivial.
5. Jalankan test, perbaiki sampai lolos.
6. Commit dengan pesan yang jelas.

## Domain & aturan data

- Transaksi: date, type (income/expense), amount, category (1 per transaksi),
  account, note opsional. TIDAK ada tag.
- Setiap query transaksi/kategori/akun/budget WAJIB difilter user_id user yang login.
- User default: admin (email/password dari environment, di-seed saat startup).
  Hanya admin yang bisa membuat user baru dan mengelola API key.
- Semua endpoint mutasi web (POST) wajib lewat origin check (CSRF).
- Password dan API key disimpan hashed (Argon2 / SHA-256), jangan pernah plaintext.

## Environment & perintah

- OS: macOS (aarch64); pakai non-interactive command.
- Python: wajib 3.13 (3.14 belum didukung pydantic-core). Venv di `.venv`.
- Install: `.venv/bin/pip install -r requirements.txt`
- Migrasi: `.venv/bin/alembic upgrade head`
- Jalankan dev: `.venv/bin/uvicorn app.main:app --reload`
- Test/self-check: `.venv/bin/python -m pytest tests/` (kalau ada), atau
  `.venv/bin/python tests/self_check.py`
- Jangan menjalankan `alembic revision --autogenerate` tanpa basis SQLite
  sementara; konfigurasi DB ada di `app/config.py` via env `DATABASE_URL`.

## Konvensi

- Ikuti gaya kode yang sudah ada di project ini.
- Nama file dan fungsi: jelas, deskriptif, bahasa Inggris.
- Komentar hanya untuk bagian yang tidak jelas, bukan menjelaskan ulang kode.
- Jangan menambah dependency kalau bisa pakai stdlib/alat bawaan.
- Perubahan skema DB WAJIB lewat migration Alembic baru, bukan edit tabel manual.
