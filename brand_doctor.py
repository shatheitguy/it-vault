#!/usr/bin/env python3
"""Report why a branding or letterhead upload is failing.

    docker exec itvault python brand_doctor.py

Reads the same configuration the app does and checks, in order, everything an
upload has to get past: the running build, the data directory, the database
connection, the columns the images live in, the server's own limits, the
image libraries, and finally how long a realistic write actually takes.

Nothing here changes your data. The write test uses a scratch table it
creates and drops; the Settings row is only ever read.
"""
import io
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FAILS = []
WARNS = []


def _c(code, s):
    return s if not sys.stdout.isatty() else f"\033[{code}m{s}\033[0m"


def head(t):
    print("\n" + _c("1", t))


def ok(label, detail=""):
    print(f"  {_c('32', 'ok')}    {label}" + (f"   {detail}" if detail else ""))


def warn(label, detail=""):
    WARNS.append(label)
    print(f"  {_c('33', 'warn')}  {label}" + (f"   {detail}" if detail else ""))


def fail(label, detail=""):
    FAILS.append(label)
    print(f"  {_c('31', 'FAIL')}  {label}" + (f"   {detail}" if detail else ""))


def info(label, detail=""):
    print(f"  {_c('2', '-')}     {label}" + (f"   {detail}" if detail else ""))


print(_c("1", "IT-Vault branding diagnostics"))

# ---------------------------------------------------------------- the build
head("1. Which build is running")
try:
    import app  # noqa: E402  -- imported after sys.path is set
except Exception as e:
    fail("app.py could not be imported", repr(e))
    print("\nNothing else can be checked without it.")
    sys.exit(1)

try:
    version = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION")).read().strip()
except Exception:
    version = "unknown"
info("VERSION", version)

# VERSION alone does not identify a build -- several commits shipped as 1.7.0.
# These are the fixes an upload depends on, so their presence is the real test.
expected = {
    "serves branding from the database": "_brand_send",
    "releases connections on failure": "_release_db_connections",
    "bounds the image before storing": "_fit_png",
    "configurable query timeout": "DB_TIMEOUT",
    "validates by file signature": "_sniff_image",
}
missing = [name for name, attr in expected.items() if not hasattr(app, attr)]
if missing:
    fail("this build predates the branding fixes", "missing: " + ", ".join(missing))
    info("", "pull ghcr.io/shatheitguy/it-vault:latest and RECREATE the container")
    info("", "(docker restart reuses the old image)")
else:
    ok("all branding fixes present in the running code")

# ------------------------------------------------------------ data directory
head("2. Data directory (only a cache -- uploads work without it)")
info("DATA_DIR", app.DATA_DIR)
writable = app._dir_writable(app.DATA_DIR)
if writable:
    ok("writable")
else:
    warn("not writable by this process",
         f"uid {os.getuid() if hasattr(os, 'getuid') else '?'}")
    info("", "fix once:  docker run --rm -v itvault_data:/data alpine chown -R 1000:1000 /data")
    info("", "uploads still work -- images are served from the database")

# ---------------------------------------------------------------- database
head("3. Database")
info("host / db", f"{app.DB_HOST}:{app.DB_PORT} / {app.DB_NAME}")
info("query timeout", f"{app.DB_TIMEOUT}s  (ITVAULT_DB_TIMEOUT)")
try:
    t0 = time.time()
    c = app.conn()
    cur = c.cursor()
    cur.execute("SELECT VERSION() AS v")
    server = (cur.fetchone() or {}).get("v", "?")
    ok("connected", f"{server}  in {(time.time() - t0) * 1000:.0f}ms")
except Exception as e:
    fail("cannot connect", repr(e))
    print("\nFix the connection first; nothing below can run.")
    sys.exit(1)

# ------------------------------------------------------------- the columns
head("4. Columns the images are stored in")
BLOBS = {"logo": "mediumblob", "letterhead": "mediumblob"}
try:
    cur.execute(
        "SELECT COLUMN_NAME, DATA_TYPE, COLUMN_TYPE FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='Settings'", [app.DB_NAME])
    cols = {r["COLUMN_NAME"].lower(): (r["DATA_TYPE"] or "").lower() for r in cur.fetchall()}
except Exception as e:
    cols = {}
    warn("could not read information_schema", repr(e))

for name, want in BLOBS.items():
    have = cols.get(name)
    if have is None:
        fail(f"Settings.{name} does not exist",
             f"run:  ALTER TABLE Settings ADD COLUMN {name} MEDIUMBLOB;")
    elif "blob" not in have:
        # this is the case a restart cannot repair: ADD COLUMN is skipped
        # because the column exists, but it cannot hold binary
        fail(f"Settings.{name} is {have.upper()}, not a BLOB",
             f"run:  ALTER TABLE Settings MODIFY {name} MEDIUMBLOB;")
    else:
        ok(f"Settings.{name}", have.upper())

if "has_letterhead" not in cols:
    warn("Settings.has_letterhead missing", "run:  ALTER TABLE Settings ADD COLUMN has_letterhead TINYINT DEFAULT 0;")
else:
    ok("Settings.has_letterhead", cols["has_letterhead"].upper())

# --------------------------------------------------------- what is in there
head("5. What is stored right now")
try:
    cur.execute("SELECT LENGTH(logo) AS l, LENGTH(letterhead) AS h, has_letterhead AS f "
                "FROM Settings WHERE id=1")
    r = cur.fetchone() or {}
    for label, key in (("logo", "l"), ("letterhead", "h")):
        n = r.get(key)
        if n:
            ok(f"{label} stored", f"{n / 1024:.0f} KB")
        else:
            info(f"{label} stored", "nothing yet")
    info("has_letterhead flag", str(r.get("f")))
except Exception as e:
    warn("could not measure stored branding", repr(e))

# ------------------------------------------------------------ server limits
head("6. Server limits that can refuse a large write")
for var, floor, note in (
    ("max_allowed_packet", 8 * 1024 * 1024, "an image larger than this is rejected outright"),
    ("wait_timeout", 60, "how long an idle connection survives"),
    ("innodb_lock_wait_timeout", 10, "how long a blocked write waits for a lock"),
    ("net_write_timeout", 30, "how long the server waits while sending to us"),
):
    try:
        cur.execute(f"SHOW VARIABLES LIKE '{var}'")
        row = cur.fetchone() or {}
        val = row.get("Value") or row.get("value")
        num = int(val) if val and str(val).isdigit() else None
        text = f"{num / 1048576:.0f} MB" if var == "max_allowed_packet" and num else str(val)
        if num is not None and num < floor:
            warn(f"{var} = {text}", note)
        else:
            ok(f"{var} = {text}")
    except Exception:
        info(var, "could not read")

# ---------------------------------------------------------- image libraries
head("7. Image libraries")
try:
    from PIL import Image  # noqa: F401
    ok("Pillow importable", "needed to normalise an uploaded image")
except Exception as e:
    fail("Pillow missing", f"{e!r} -- an image letterhead cannot be converted")
try:
    import pymupdf  # noqa: F401
    ok("PyMuPDF importable", "needed to rasterise a PDF letterhead")
except Exception as e:
    fail("PyMuPDF missing", f"{e!r} -- a PDF letterhead cannot be converted")

# -------------------------------------------------------------- write speed
head("8. How long a realistic write actually takes")
info("", "scratch table, created and dropped -- your data is untouched")
try:
    cur.execute("CREATE TABLE IF NOT EXISTS _itvault_brand_diag (id INT PRIMARY KEY, blob_col MEDIUMBLOB)")
    c.commit()
    for kb in (64, 512, 2048):
        payload = os.urandom(kb * 1024)
        try:
            t0 = time.time()
            cur.execute("REPLACE INTO _itvault_brand_diag (id, blob_col) VALUES (1, %s)", (payload,))
            c.commit()
            dt = time.time() - t0
            rate = (kb / 1024) / dt if dt > 0 else 0
            line = f"{dt:.1f}s  ({rate:.1f} MB/s)"
            if dt > app.DB_TIMEOUT * 0.5:
                warn(f"{kb} KB write", line + f"  -- over half the {app.DB_TIMEOUT}s timeout")
            else:
                ok(f"{kb} KB write", line)
        except Exception as e:
            fail(f"{kb} KB write failed", repr(e))
            break
    cur.execute("DROP TABLE IF EXISTS _itvault_brand_diag")
    c.commit()
    ok("scratch table dropped")
except Exception as e:
    warn("write test could not run", repr(e))

try:
    c.close()
except Exception:
    pass

# ------------------------------------------------------------------ summary
head("Summary")
if FAILS:
    print(f"  {_c('31', str(len(FAILS)) + ' problem(s)')}: " + "; ".join(FAILS))
    print("\n  Each FAIL above prints the command that fixes it.")
elif WARNS:
    print(f"  {_c('33', 'no failures, ' + str(len(WARNS)) + ' warning(s)')}: " + "; ".join(WARNS))
    print("\n  Uploads should work. If one still fails, the warnings above are")
    print("  the most likely cause -- send this whole output over.")
else:
    print(f"  {_c('32', 'Everything an upload needs is in place.')}")
    print("\n  If an upload still fails, the problem is in the request itself:")
    print("  open the browser's Network tab, retry it, and send the response")
    print("  body of the failing PUT /api/settings.")
sys.exit(1 if FAILS else 0)
