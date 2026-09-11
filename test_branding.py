#!/usr/bin/env python3
"""Branding upload regression tests. Needs a real database.

    python test_branding.py                 # uses itvault_config.json / DB_* env

These exist because the branding upload broke in a way no stub could catch. A
request took a row lock on Settings id=1 with the big settings UPDATE, then
opened a SECOND connection to write the logo into that same row -- deadlocking
against itself until innodb_lock_wait_timeout. Every mock I wrote passed
happily; only a real InnoDB row lock reproduces it.

The first test asserts the hazard is still real (a second connection IS
blocked), so the rest cannot quietly stop testing anything. It writes to the
Settings row of whatever database it is pointed at, so point it at a test one.
"""
import io
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pymysql  # noqa: E402
import app as A  # noqa: E402

try:
    from PIL import Image
except Exception:
    print("Pillow is required for these tests")
    sys.exit(2)

FAILS = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (f"   {detail}" if detail else ""))
    if not cond:
        FAILS.append(name)


def db():
    """A raw connection, separate from the app's pool -- these tests are about
    what happens between two connections, so they must not share one."""
    return pymysql.connect(
        host=A.DB_HOST, port=int(A.DB_PORT), user=A.DB_USER, password=A.DB_PASS,
        database=A.DB_NAME, cursorclass=pymysql.cursors.DictCursor, connect_timeout=5)


def png(w, h, colour=(255, 59, 48)):
    b = io.BytesIO()
    Image.new("RGB", (w, h), colour).save(b, format="PNG")
    return b.getvalue()


print(f"branding tests against {A.DB_USER}@{A.DB_HOST}:{A.DB_PORT}/{A.DB_NAME}")
try:
    db().close()
except Exception as e:
    print(f"\ncannot reach the database: {e}")
    print("point DB_* or itvault_config.json at one and try again")
    sys.exit(2)

IMG = png(300, 120)

# ---------------------------------------------------------------- the hazard
print("\n1. The row lock this bug depended on is real")
holder = db()
hcur = holder.cursor()
hcur.execute("SET SESSION innodb_lock_wait_timeout=3")
hcur.execute("UPDATE Settings SET theme=theme WHERE id=1")   # lock, do not commit
other = db()
ocur = other.cursor()
ocur.execute("SET SESSION innodb_lock_wait_timeout=3")
t0 = time.time()
blocked, err = False, None
try:
    ocur.execute("UPDATE Settings SET logo=%s WHERE id=1", (IMG,))
    other.commit()
except Exception as e:
    blocked, err = True, str(e)[:60]
dt = time.time() - t0
check("a second connection is blocked writing the locked row", blocked, f"{dt:.1f}s {err or ''}")
other.close()
holder.rollback()
holder.close()

# ------------------------------------------------------------------ the fix
print("\n2. _brand_store joins the caller's transaction instead of opening one")
c = db()
cur = c.cursor()
cur.execute("SET SESSION innodb_lock_wait_timeout=3")
cur.execute("UPDATE Settings SET theme=theme WHERE id=1")    # hold the lock
t0 = time.time()
ok, err = A._brand_store("logo", A.LOGO_PATH, IMG, cur=cur)
dt = time.time() - t0
c.commit()
c.close()
check("the write succeeds", ok is True, str(err or ""))
check("without waiting on the lock", dt < 1.0, f"{dt:.2f}s")

# ------------------------------------------------------------- the HTTP path
print("\n3. PUT /api/settings with a logo, and with a letterhead")
A.app.config["TESTING"] = True
cl = A.app.test_client()
with cl.session_transaction() as s:
    s["user"] = "admin"
    s["role"] = "admin"

t0 = time.time()
r = cl.put("/api/settings", content_type="multipart/form-data", data={
    "app_name": "IT-Vault", "logo_text": "IT-Vault",
    "company_phone": "", "company_address": "",
    "logo": (io.BytesIO(IMG), "logo.png")})
dt = time.time() - t0
check("logo save returns 200", r.status_code == 200, f"{r.status_code} {r.get_data(as_text=True)[:80]}")
check("logo save does not stall", dt < 5.0, f"{dt:.2f}s")

LH = png(1200, 1700, (250, 250, 250))
t0 = time.time()
r = cl.put("/api/settings", content_type="multipart/form-data",
           data={"letterhead": (io.BytesIO(LH), "letterhead.png")})
dt = time.time() - t0
check("letterhead save returns 200", r.status_code == 200, f"{r.status_code} {r.get_data(as_text=True)[:80]}")
check("letterhead save does not stall", dt < 10.0, f"{dt:.2f}s")

# -------------------------------------------------------------- and it stuck
print("\n4. Both are in the database and serve back")
c = db()
cur = c.cursor()
cur.execute("SELECT LENGTH(logo) l, LENGTH(letterhead) h, has_letterhead f FROM Settings WHERE id=1")
row = cur.fetchone()
c.close()
check("logo stored", bool(row["l"]), f"{row['l']} bytes")
check("letterhead stored", bool(row["h"]), f"{row['h']} bytes")
check("has_letterhead set", row["f"] == 1, str(row["f"]))
for path in ("/logo.png", "/letterhead.png"):
    rr = cl.get(path)
    check(f"GET {path}", rr.status_code == 200 and len(rr.get_data()) > 100,
          f"{rr.status_code}, {len(rr.get_data())} bytes")

# ---------------------------------------------------------------- rejections
print("\n5. What must still be refused")
r = cl.put("/api/settings", content_type="multipart/form-data",
           data={"app_name": "IT-Vault", "logo_text": "IT-Vault",
                 "company_phone": "", "company_address": "",
                 "logo": (io.BytesIO(b'<svg xmlns="http://www.w3.org/2000/svg"/>'), "x.png")})
check("an SVG named .png is refused", r.status_code == 400, str(r.status_code))
check("and says what is accepted", "PNG" in r.get_data(as_text=True), r.get_data(as_text=True)[:80])

print("\n" + ("ALL PASSED" if not FAILS else f"{len(FAILS)} FAILED: " + ", ".join(FAILS)))
sys.exit(1 if FAILS else 0)
