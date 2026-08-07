"""Self-check: verifies core logic without needing a running DB server.

Runs against an in-memory SQLite database.
"""
import datetime
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Use a temp SQLite DB for the check
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database import Base  # noqa: E402
from app.models import Category, Transaction, User  # noqa: E402
from app.security import (  # noqa: E402
    create_session_token,
    generate_api_key,
    hash_api_key,
    hash_password,
    rate_limit,
    read_session_token,
    verify_password,
)

engine = create_engine(f"sqlite:///{_tmp.name}")
Session = sessionmaker(bind=engine)
Base.metadata.create_all(engine)

failures = []


def check(name, cond):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(name)


# --- security ---
pw = hash_password("s3cret!")
check("password hash/verify", verify_password("s3cret!", pw) and not verify_password("wrong", pw))
check("password not plaintext", "s3cret!" not in pw)

uid = "user-1"
token = create_session_token(uid)
check("session token roundtrip", read_session_token(token) == uid)
check("session token tamper", read_session_token(token + "x") is None)

key = generate_api_key()
check("api key format", key.startswith("ft_") and len(key) > 20)
check("api key hashed", hash_api_key(key) != key and hash_api_key(key) == hash_api_key(key))

rl_key = "test-rl"
allowed = all(rate_limit(rl_key, limit=3, window_seconds=60) for _ in range(3))
check("rate limit allows under limit", allowed)
check("rate limit blocks over limit", not rate_limit(rl_key, limit=3, window_seconds=60))

# --- models ---
db = Session()
u = User(id=uid, email="admin@test.dev", password_hash=pw, is_admin=True)
db.add(u)
db.commit()

c = Category(user_id=uid, name="Makan", type="expense")
db.add(c)
db.commit()

t = Transaction(user_id=uid, date=datetime.date(2026, 8, 7), type="expense", amount=50000, category_id=c.id, note="Warteg")
db.add(t)
db.commit()

check("transaction persist", db.get(Transaction, t.id) is not None)
check("transaction fields", t.type == "expense" and float(t.amount) == 50000.0 and t.note == "Warteg")

# cleanup temp db
db.close()
os.unlink(_tmp.name)

print()
if failures:
    print(f"FAILED: {len(failures)} check(s)")
    sys.exit(1)
print("ALL CHECKS PASSED")
