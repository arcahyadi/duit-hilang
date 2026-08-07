#!/bin/sh
# Start app: HTTPS jika SSL_CERTFILE/SSL_KEYFILE diisi, HTTP jika tidak.
set -e
alembic upgrade head
if [ -n "$SSL_CERTFILE" ] && [ -n "$SSL_KEYFILE" ]; then
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000 \
    --ssl-certfile "$SSL_CERTFILE" --ssl-keyfile "$SSL_KEYFILE"
else
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000
fi
