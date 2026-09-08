# IT-Vault -- self-hosted IT asset and helpdesk manager.
# Copyright (C) 2026 Sharqan Ahamed (Sha The IT Guy)
#
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public
# License for more details. You should have received a copy of it along with
# this program; if not, see <https://www.gnu.org/licenses/>.
"""
IT-Vault — Flask + MariaDB backend.
Roles: admin (full), read-write (assets CRUD), read-only (view + own password).
Docker-ready. No Access DB.
"""
import os, io, json, hashlib, uuid, secrets, time, base64, re, zipfile, threading, sys
from datetime import timedelta, datetime
from urllib.parse import quote, unquote
from flask import Flask, request, jsonify, Response, session, send_from_directory, redirect, make_response
from flask import g, has_request_context
import pymysql
from dbutils.pooled_db import PooledDB
from openpyxl import Workbook, load_workbook
import ldap3
import pyotp
import qrcode
import qrcode.image.svg

BASE = os.path.dirname(os.path.abspath(__file__))
INVOICE_DIR = os.path.join(BASE, "invoices")
os.makedirs(INVOICE_DIR, exist_ok=True)

# State that must outlive the code it sits next to: the DB pointer and the
# session-signing key. In a container the image is replaced on every update,
# so these live in DATA_DIR, which deployments mount as a volume. Defaults to
# the app directory, which is what a source checkout wants.
DATA_DIR = os.environ.get("ITVAULT_DATA_DIR") or BASE
try:
    os.makedirs(DATA_DIR, exist_ok=True)
except Exception:
    DATA_DIR = BASE

# ---- persistent DB config (itvault_config.json) ----
# Lets you point the app at a different MariaDB container/server from the UI.
# Uploaded branding belongs with the rest of the persistent state, not in the
# image. Written to BASE it lived in the container's writable layer, so every
# update -- which replaces the container -- silently wiped the logo and
# letterhead. (default_logo.png stays in BASE: it ships with the image.)
LOGO_PATH = os.path.join(DATA_DIR, "logo.png")
LETTERHEAD_PATH = os.path.join(DATA_DIR, "letterhead.png")


def _dir_writable(path):
    """Can this process actually create a file in here?

    os.access() consults the mode bits and gets this wrong often enough to be
    useless -- a root-owned Docker volume mounted under a non-root USER is
    exactly the case it misreports. So try it for real.
    """
    probe = os.path.join(path, ".itvault_write_probe")
    try:
        with open(probe, "wb") as fp:
            fp.write(b"1")
        os.remove(probe)
        return True
    except Exception:
        return False


# A named volume is created empty and root-owned unless the image already
# contains the directory it shadows, and the container runs as uid 1000. When
# that happens every write in here fails, which used to take the uploaded
# branding, the saved database pointer and the session key down with it.
# Nothing may depend on this being True.
DATA_DIR_WRITABLE = _dir_writable(DATA_DIR)
if not DATA_DIR_WRITABLE:
    print(f"[itvault] WARNING: {DATA_DIR} is not writable by this process "
          f"(uid {os.getuid() if hasattr(os, 'getuid') else '?'}). Branding and "
          f"settings are still safe -- they live in the database -- but fix the "
          f"volume with:  docker run --rm -v itvault_data:/data alpine "
          f"chown -R 1000:1000 /data", flush=True)


def _brand_blob(col):
    """The stored logo/letterhead bytes, or None.

    The file on disk is only ever a cache. The database is what actually
    survives a container being replaced, so it is the source of truth -- which
    is why branding used to vanish on update even though it was still in here.
    """
    try:
        c = conn(); cur = c.cursor()
        cur.execute("SELECT `%s` FROM Settings WHERE id=1" % col)
        r = cur.fetchone(); c.close()
        return (r or {}).get(col) or None
    except Exception:
        return None


# What we are willing to push into a single INSERT. A PDF page rasterized at
# 144dpi can be several megabytes, and sending that to a database over a slow
# or TLS-wrapped link is what made the letterhead save time out.
BRAND_MAX_BYTES = 3 * 1024 * 1024
BRAND_MAX_EDGE = 1600
# A logo is a mark in a sidebar and on a printed label, never a page: no
# surface renders it above a couple of hundred pixels. Shrinking an
# oversized one is a better answer than refusing it, which is what a hard
# 500KB cap did -- and it is the same treatment the letterhead gets.
LOGO_MAX_EDGE = 512
LOGO_MAX_BYTES = 400 * 1024


def _fit_png(data, max_edge=BRAND_MAX_EDGE, max_bytes=BRAND_MAX_BYTES):
    """Bring a rendered image within something one statement can carry.

    1600px is already more than the print surfaces use (A4 at 144dpi is
    1191px wide), so the cap costs nothing visible; if the result is still
    over budget it steps down until it fits.

    Every candidate is measured and the smallest kept, and the original wins
    if nothing beat it -- re-encoding at a smaller size is not guaranteed to
    produce fewer bytes (downscaling averages neighbouring pixels, which can
    cost more entropy than the dropped pixels saved), and returning something
    larger than what came in would defeat the point. Without PIL, or on any
    failure, the input is returned untouched rather than losing the upload.
    """
    try:
        from PIL import Image as PILImage
        img = PILImage.open(io.BytesIO(data))
        w, h = img.size
    except Exception:
        return data
    if w <= max_edge and h <= max_edge and len(data) <= max_bytes:
        return data
    best = data
    for edge in (max_edge, 1200, 900, 700):
        if edge >= max(w, h) and len(data) <= max_bytes:
            continue
        try:
            im = PILImage.open(io.BytesIO(data))
            im.thumbnail((edge, edge))
            buf = io.BytesIO()
            im.convert("RGB").save(buf, format="PNG", optimize=True)
            cand = buf.getvalue()
        except Exception:
            break
        if len(cand) < len(best):
            best = cand
        if len(best) <= max_bytes:
            break
    return best


def _brand_store(col, path, data):
    """Save branding to the database, and cache it on disk if we can.

    Returns (ok, error). Only the database write decides that: the file is a
    convenience, and on an install whose data volume is root-owned it can
    never succeed. Failing the upload over it -- or swallowing a real database
    error so the upload merely looks like it worked -- is what made this
    impossible to diagnose from the UI.
    """
    c = None
    try:
        c = conn(); cur = c.cursor()
        cur.execute("UPDATE Settings SET `%s`=%%s WHERE id=1" % col, (data,))
        # An UPDATE matching no row is a success that changed nothing. If the
        # Settings row is missing there is no error to see, and the image
        # simply never appears -- so the row count is checked, not assumed.
        touched = cur.rowcount
        c.commit()
        if touched == 0:
            cur.execute("SELECT COUNT(*) AS n FROM Settings WHERE id=1")
            if not (cur.fetchone() or {}).get("n"):
                print(f"[itvault] {col}: no Settings row with id=1 -- nothing was saved", flush=True)
                return False, ("This database has no settings row yet. Restart IT-Vault so it "
                               "can create one, then try the upload again.")
    except Exception as e:
        # Rolled back and released explicitly rather than relying on the
        # request teardown: this also runs from the scheduled jobs, which have
        # no request to tear down. Leaving it open held the lock on Settings
        # id=1 and made every later settings save time out too.
        if c is not None:
            try: c.rollback()
            except Exception: pass
        print(f"[itvault] could not store {col} in the database: {e}", flush=True)
        return False, _brand_store_help(col, e)
    finally:
        if c is not None:
            try: c.close()
            except Exception: pass
    try:
        with open(path, "wb") as fp:
            fp.write(data)
    except Exception as e:
        print(f"[itvault] {col} saved to the database but not cached at {path}: {e}", flush=True)
    return True, None


def _brand_store_help(col, exc):
    """Turn a driver error on a branding write into something actionable."""
    msg = str(exc)
    code = exc.args[0] if getattr(exc, "args", None) else None
    if code in (1406, 1366) or "Data too long" in msg or "Incorrect string value" in msg:
        return (f"The Settings.{col} column can't hold image data on this database. "
                f"Run:  ALTER TABLE Settings MODIFY {col} MEDIUMBLOB;")
    if code == 1054 or "Unknown column" in msg:
        return (f"This database has no Settings.{col} column. Restart IT-Vault so it "
                f"can add it, or run:  ALTER TABLE Settings ADD COLUMN {col} MEDIUMBLOB;")
    if code == 1153 or "max_allowed_packet" in msg:
        return ("The image is larger than the database will accept in one statement. "
                "Use a smaller file, or raise max_allowed_packet on the server.")
    if code in (2013, 2006) or "Lost connection" in msg or "timed out" in msg:
        return ("The database stopped responding while the image was being saved. "
                "That usually means the file is large and the connection to the "
                "database is slow -- try a smaller image. If it keeps happening, "
                "raise ITVAULT_DB_TIMEOUT (currently "
                f"{DB_TIMEOUT}s) or move the database closer to the app.")
    return f"Database rejected the upload: {msg}"


def _brand_restore(col, path):
    """Re-create the on-disk cache from the database when it's missing.

    Called by the serving routes, so the first request after an update quietly
    repopulates the file instead of showing a blank logo. Returns False when
    there is nothing stored OR the cache can't be written -- callers fall back
    to serving the bytes straight out of the database.
    """
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return True
    data = _brand_blob(col)
    if not data:
        return False
    try:
        with open(path, "wb") as fp:
            fp.write(data)
        print(f"[itvault] restored {col} from the database", flush=True)
        return True
    except Exception:
        return False


def _brand_send(col, path, filename):
    """Serve branding from the disk cache, or straight from the database.

    The database path is what keeps the logo visible on an install whose data
    volume the app can't write to -- there, the cache never materializes and
    every request would otherwise fall through to the default mark.
    """
    if _brand_restore(col, path) and os.path.exists(path) and os.path.getsize(path) > 0:
        return send_from_directory(DATA_DIR, filename)
    data = _brand_blob(col)
    if not data:
        return None
    resp = make_response(bytes(data))
    resp.headers["Content-Type"] = "image/png"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp

def _migrate_branding_to_data_dir():
    """Move a logo/letterhead left in BASE by an older build into DATA_DIR.

    Runs once, on the first start after upgrading, so an install that already
    had branding keeps it instead of coming up blank.
    """
    if DATA_DIR == BASE:
        return
    import shutil
    for name, dest in (("logo.png", LOGO_PATH), ("letterhead.png", LETTERHEAD_PATH)):
        src = os.path.join(BASE, name)
        try:
            if (os.path.exists(src) and os.path.getsize(src) > 0
                    and not (os.path.exists(dest) and os.path.getsize(dest) > 0)):
                shutil.copy2(src, dest)
                print(f"[itvault] migrated {name} into {DATA_DIR}", flush=True)
        except Exception as e:
            print(f"[itvault] could not migrate {name}: {e}", flush=True)


_migrate_branding_to_data_dir()

CONFIG_PATH = os.path.join(DATA_DIR, "itvault_config.json")
def load_config():
    """An install with no config file lands on the first-run setup wizard,
    which writes this file once a database has been entered and tested."""
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH) as f:
                return json.load(f) or {}
    except Exception:
        pass
    return {}
_cfg = load_config()
DB_HOST = _cfg.get("db_host", os.environ.get("DB_HOST", "127.0.0.1"))
DB_PORT = int(_cfg.get("db_port", os.environ.get("DB_PORT", 3306)))
DB_NAME = _cfg.get("db_name", os.environ.get("DB_NAME", "itguy_assets"))
DB_USER = _cfg.get("db_user", os.environ.get("DB_USER", "itguy"))
DB_PASS = _cfg.get("db_pass", os.environ.get("DB_PASS", "itguypass"))
# How long a query may stall before the request gives up on it. A bound is
# essential (see the pool below), but 30s is not always enough for a large
# letterhead going over a slow or TLS-wrapped link, so it is raisable without
# rebuilding the image.
try:
    DB_TIMEOUT = max(5, int(os.environ.get("ITVAULT_DB_TIMEOUT") or 30))
except Exception:
    DB_TIMEOUT = 30
def save_db_config(h, p, n, u, pw):
    global DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS = h, int(p), n, u, pw
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump({"db_host": h, "db_port": int(p), "db_name": n, "db_user": u, "db_pass": pw}, f, indent=2)
    except Exception:
        pass
def persist_env_db_config():
    """Record environment-provided database credentials in the config file.

    install.sh passes DB_HOST/DB_NAME/DB_USER/DB_PASS as container
    environment, and that is the ONLY place they live. So `docker rm -f
    itvault` followed by a plain `docker run` loses them and the setup wizard
    asks for a database again -- on an install that already had a perfectly
    good one. Recording them changes nothing about how they resolve, since
    load_config() already takes precedence over the environment; it just
    means the pointer outlives the container that was told it.

    Only ever called once the database has actually answered, so a typo in
    the environment is never written down as though it worked. An existing
    entry is left alone: a value set through Settings is the user's, not the
    environment's.
    """
    if _cfg.get("db_host"):
        return False
    if not (os.environ.get("DB_HOST") or os.environ.get("DB_NAME")):
        return False
    before = os.path.exists(CONFIG_PATH)
    save_db_config(DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS)
    if os.path.exists(CONFIG_PATH):
        _cfg["db_host"] = DB_HOST
        print(f"[itvault] database pointer saved to {CONFIG_PATH} -- it now "
              f"survives the container being replaced", flush=True)
        return True
    print(f"[itvault] could not write {CONFIG_PATH}"
          + ("" if before else " (directory not writable?)")
          + " -- the database pointer will be lost when this container is "
            "replaced, and the setup wizard will ask again", flush=True)
    return False


# ---- first-run setup state ----
# The app has to be able to boot with NO working database, otherwise there's
# nowhere to ask the user for one -- so instead of refusing to start, it
# serves a setup wizard until a database answers and an admin exists.
_setup_done = False

def _db_reachable(host=None, port=None, name=None, user=None, pw=None) -> bool:
    try:
        c = pymysql.connect(host=host or DB_HOST, port=int(port or DB_PORT),
                            user=user or DB_USER, password=DB_PASS if pw is None else pw,
                            database=name or DB_NAME, charset="utf8mb4",
                            cursorclass=pymysql.cursors.DictCursor, connect_timeout=5)
        c.close()
        return True
    except Exception:
        return False

def setup_needed() -> bool:
    """True until there's a database we can reach AND at least one login in
    it. Latches to False once satisfied so the normal request path isn't
    paying for a probe on every hit -- and so a later database blip shows as
    an error rather than silently reopening the setup wizard to the network."""
    global _setup_done
    if _setup_done:
        return False
    try:
        c = conn(); cur = c.cursor()
        cur.execute("SELECT COUNT(*) AS n FROM Users")
        n = (cur.fetchone() or {}).get("n") or 0
        c.close()
        if n > 0:
            _setup_done = True
            return False
        return True
    except Exception:
        return True

# ---- release identity + update checks ----
def _read_version():
    try:
        # utf-8-sig: a VERSION file saved by a Windows editor carries a BOM,
        # which strip() leaves in place and version comparisons then choke on
        with open(os.path.join(BASE, "VERSION"), encoding="utf-8-sig") as f:
            v = f.read().strip()
            if v:
                return v
    except Exception:
        pass
    return "0.0.0-dev"

APP_VERSION = _read_version()

# Where update checks look for new releases, as GitHub "owner/repo". Baked in
# so a normal install needs no configuration at all; ITVAULT_UPDATE_REPO only
# exists to point a fork or a private mirror somewhere else.
DEFAULT_UPDATE_REPO = "shatheitguy/it-vault"

def update_repo():
    return (_env("ITVAULT_UPDATE_REPO", default="") or DEFAULT_UPDATE_REPO or "").strip().strip("/")

def _in_docker():
    """Docker installs upgrade by pulling a new image, not by touching files
    in place, so the update advice has to differ. ITVAULT_DOCKER is set by
    the Dockerfile; /.dockerenv is the fallback for images built elsewhere."""
    if os.environ.get("ITVAULT_DOCKER") == "1":
        return True
    try:
        return os.path.exists("/.dockerenv")
    except Exception:
        return False

IS_DOCKER = _in_docker()

def _watchtower():
    """Where to ask Watchtower to apply a container update, or None.

    A container cannot replace itself: that needs the host's Docker socket,
    and mounting the socket into a web app which also handles uploads, LDAP
    and SMTP hands it root-equivalent control of the machine. Watchtower
    already does exactly this job from a small single-purpose container and
    exposes an HTTP trigger, so IT-Vault asks it to update and never holds
    the socket itself. Returns (base_url, token)."""
    token = (_env("ITVAULT_WATCHTOWER_TOKEN", default="") or "").strip()
    if not token:
        return None
    url = (_env("ITVAULT_WATCHTOWER_URL", default="")
           or "http://watchtower:8080").strip().rstrip("/")
    return url, token

def _update_method():
    """How this install can update itself in one click: 'watchtower' for a
    container with Watchtower reachable, 'source' for a git checkout, or ''
    when the update has to be applied by hand."""
    if IS_DOCKER:
        return "watchtower" if _watchtower() else ""
    try:
        return "source" if os.path.isdir(os.path.join(BASE, ".git")) else ""
    except Exception:
        return ""

def _restart_self():
    """Re-exec this process so freshly pulled code takes effect. Delayed so
    the response reaches the browser before the listening socket closes."""
    time.sleep(1.5)
    try:
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception:
        # a supervisor (systemd, or Docker's restart policy) brings it back
        os._exit(3)

def _version_tuple(v):
    """'v1.6.0' / '1.6' / '1.6.0-rc1' -> comparable (1,6,0). Any trailing
    pre-release suffix is dropped, so a tagged release always sorts above a
    release candidate of the same number rather than comparing as text."""
    v = str(v or "").strip().lstrip("vV").split("+")[0].split("-")[0]
    parts = []
    for chunk in v.split(".")[:3]:
        try:
            parts.append(int(chunk))
        except ValueError:
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)

SECRET_KEY_PATH = os.path.join(DATA_DIR, ".secret_key")

def _env(*names, default=None):
    """First of `names` that's actually set. Lets settings be renamed to the
    IT-Vault branding while still honouring the old ITGUY_* names, so an
    existing deployment doesn't silently change behaviour on upgrade -- for
    the session secret in particular, ignoring the old name would mint a new
    one and log every user out."""
    for n in names:
        v = os.environ.get(n)
        if v:
            return v
    return default

def _load_or_create_secret():
    """Flask signs session cookies with this. It must never be a hardcoded,
    guessable default -- anyone who knows it can forge an admin session
    without a password. Prefer ITVAULT_SECRET (ITGUY_SECRET still honoured);
    otherwise generate one and persist it locally so it survives restarts but
    never lands in git."""
    env_secret = _env("ITVAULT_SECRET", "ITGUY_SECRET")
    if env_secret:
        return env_secret
    try:
        if os.path.exists(SECRET_KEY_PATH):
            with open(SECRET_KEY_PATH) as f:
                v = f.read().strip()
                if v:
                    return v
    except Exception:
        pass
    v = secrets.token_hex(32)
    try:
        with open(SECRET_KEY_PATH, "w") as f:
            f.write(v)
        try:
            os.chmod(SECRET_KEY_PATH, 0o600)
        except Exception:
            pass
    except Exception:
        pass
    return v
SECRET = _load_or_create_secret()
ADMIN_USER = _env("ITVAULT_ADMIN", "ITGUY_ADMIN", default="admin")
ADMIN_PASS = _env("ITVAULT_ADMIN_PASS", "ITGUY_ADMIN_PASS", default="admin123")

COLUMNS = ["AssetTag", "Name", "Type", "Serial", "MacAddress", "Location", "Status", "Manufacturer", "Model", "ReceivedBy", "NotesReceived", "Note", "PurchaseDate", "WarrantyMonths", "Price", "EmployeeID", "RequestedBy"]
INT_COLS = {"WarrantyMonths"}  # columns stored as integers
DEC_COLS = {"Price"}  # columns stored as decimals

def coerce_val(col, v):
    v = "" if v is None else v
    if col in INT_COLS:
        try:
            return int(v) if str(v).strip() != "" else 0
        except Exception:
            return 0
    if col in DEC_COLS:
        try:
            return float(v) if str(v).strip() != "" else 0.0
        except Exception:
            return 0.0
    return str(v)
STATUSES = ["Available", "Checked-Out", "Under-Maintenance", "Reserved", "Retired", "Lost/Stolen"]
# role groups
ROLE_VIEW = "read-only"
ROLE_EDIT = "read-write"
ROLE_ADMIN = "admin"
ROLES = [ROLE_ADMIN, ROLE_EDIT, ROLE_VIEW]
# Built-in roles' access to the modules a custom role can be scoped to
# (assets / contracts / directory=Employees / tickets). Admin implicitly
# passes every module+level check (see auth_required), so it isn't listed.
# "settings" is 'none' for both built-ins on purpose: configuration has always
# been admin-only, and defaulting it any higher would hand every existing
# read-write/read-only account access it doesn't have today.
BUILTIN_ROLE_PERMS = {
    ROLE_EDIT: {"assets": "write", "contracts": "write", "directory": "write", "tickets": "write", "settings": "none"},
    ROLE_VIEW: {"assets": "read", "contracts": "read", "directory": "read", "tickets": "read", "settings": "none"},
}
_PERM_ORDER = {"none": 0, "read": 1, "write": 2}

def _role_perms(role_name):
    """Resolve a role name (built-in or custom, from the Roles table) to its
    per-module permission dict. Unknown roles get no access anywhere."""
    if role_name in BUILTIN_ROLE_PERMS:
        return BUILTIN_ROLE_PERMS[role_name]
    try:
        c = conn(); cur = c.cursor()
        cur.execute("SELECT perm_assets, perm_contracts, perm_directory, perm_tickets, perm_settings FROM Roles WHERE name=%s", [role_name])
        r = cur.fetchone(); c.close()
    except Exception:
        r = None
    if not r:
        return {"assets": "none", "contracts": "none", "directory": "none", "tickets": "none", "settings": "none"}
    return {"assets": r.get("perm_assets") or "none", "contracts": r.get("perm_contracts") or "none",
            "directory": r.get("perm_directory") or "none", "tickets": r.get("perm_tickets") or "none",
            "settings": r.get("perm_settings") or "none"}

# ---------- ticket photo attachments ----------
# A phone camera is the fastest bug report there is, so the portal lets a
# requester attach one. That endpoint is public, so nothing the browser says
# about the file is trusted: the type is read back out of the bytes and only
# real raster images are kept. SVG is deliberately absent -- it is a script
# carrier, and these are served from the app's own origin.
ATTACH_MAX_BYTES = 4 * 1024 * 1024
ATTACH_MAX_PER_TICKET = 4
# Signatures as hex, so the table stays readable next to the byte counts.
_IMAGE_MAGIC = (
    (bytes.fromhex("ffd8ff"), "image/jpeg", "jpg"),
    (bytes.fromhex("89504e470d0a1a0a"), "image/png", "png"),
    (b"GIF87a", "image/gif", "gif"),
    (b"GIF89a", "image/gif", "gif"),
)

def _sniff_image(data):
    """Return (mimetype, extension) for real image bytes, else (None, None).

    The signature is read from the file itself; a .png that is really a zip,
    or an SVG renamed to .jpg, does not get through."""
    if not data or len(data) < 12:
        return None, None
    for magic, mime, ext in _IMAGE_MAGIC:
        if data.startswith(magic):
            return mime, ext
    # RIFF....WEBP -- the size field sits between the two markers
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    # ISO-BMFF: HEIC/HEIF, which is what an iPhone hands over by default
    if data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand in (b"heic", b"heix", b"hevc", b"heim", b"heis", b"hevm", b"mif1", b"msf1"):
            return "image/heic", "heic"
    return None, None

def _store_ticket_photos(cur, ticket_id, files, uploaded_by):
    """Validate and save uploaded photos. Returns (saved, [skip reasons])."""
    saved, skipped = 0, []
    cur.execute("SELECT COUNT(*) AS n FROM TicketAttachments WHERE ticket_id=%s", [ticket_id])
    have = (cur.fetchone() or {}).get("n", 0) or 0
    for f in files:
        if not f or not getattr(f, "filename", ""):
            continue
        if have + saved >= ATTACH_MAX_PER_TICKET:
            skipped.append(f"{f.filename}: only {ATTACH_MAX_PER_TICKET} photos per ticket")
            continue
        data = f.read(ATTACH_MAX_BYTES + 1)
        if len(data) > ATTACH_MAX_BYTES:
            skipped.append(f"{f.filename}: over {ATTACH_MAX_BYTES // (1024 * 1024)}MB")
            continue
        mime, ext = _sniff_image(data)
        if not mime:
            skipped.append(f"{f.filename}: not a JPEG, PNG, GIF, WebP or HEIC image")
            continue
        # The stored name is ours, not theirs -- a filename from a public form
        # has no business steering a path or a header.
        name = re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(f.filename or ""))[:180] or ("photo." + ext)
        cur.execute("""INSERT INTO TicketAttachments (ticket_id, filename, mimetype, size, uploaded_by, data)
                       VALUES (%s,%s,%s,%s,%s,%s)""",
                    (ticket_id, name, mime, len(data), (uploaded_by or "portal")[:80], data))
        saved += 1
    return saved, skipped

def _ticket_hist(cur, ticket_id, who, field, old_val, new_val):
    """One row on a ticket's change trail. Same shape as an asset's history,
    which is what lets the UI render both with the same markup."""
    cur.execute("INSERT INTO TicketHistory (ticket_id, ts, user, field, old_val, new_val) "
                "VALUES (%s, NOW(), %s, %s, %s, %s)",
                [ticket_id, who, field, old_val, new_val])


def _attachment_rows(cur, ticket_id):
    """Metadata only -- the bytes are fetched one at a time by their own route."""
    cur.execute("""SELECT id, filename, mimetype, size, uploaded_by, created_at
                   FROM TicketAttachments WHERE ticket_id=%s ORDER BY id""", [ticket_id])
    # Built key by key rather than dict(row), so the image bytes can never
    # ride along into a JSON response if this SELECT is ever widened.
    return [{"id": r["id"], "filename": r.get("filename") or "photo",
             "mimetype": r.get("mimetype") or "", "size": r.get("size") or 0,
             "uploaded_by": r.get("uploaded_by") or "",
             "created_at": str(r.get("created_at") or "")} for r in cur.fetchall()]

def _attachment_response(row):
    """Send image bytes with the type WE sniffed, never the uploader's, and
    tell the browser not to second-guess it."""
    resp = make_response(row["data"])
    resp.headers["Content-Type"] = row.get("mimetype") or "application/octet-stream"
    resp.headers["Content-Disposition"] = "inline; filename=\"%s\"" % (row.get("filename") or "photo")
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return resp

def _is_admin():
    """True only for the admin role, for actions that must never fall to an
    editor -- deletion, chiefly. Mirrors _module_write_allowed()'s
    session-or-API-key resolution so it holds for the mobile app too."""
    urole = session.get("role")
    if not session.get("user"):
        row = _resolve_session_from_api_key()
        if not row:
            return False
        urole = row["role"]
    return urole == ROLE_ADMIN


def _data_dir_persistent():
    """Is DATA_DIR on a mounted volume, or will it die with the container?

    A container started without `-v itvault_data:/app/data` keeps
    itvault_config.json in its writable layer, so replacing the container --
    which is exactly how you update it -- silently throws away the database
    pointer and the session key, and the next start lands on the setup wizard.
    Better to say so up front than let someone find out mid-upgrade.
    """
    if not IS_DOCKER:
        return True
    try:
        with open("/proc/self/mountinfo", encoding="utf-8") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) > 4 and parts[4] == DATA_DIR:
                    return True
        return False
    except Exception:
        return True          # never cry wolf on a platform we can't inspect


def _db_error_help(exc, host=""):
    """A driver error, rewritten as something a person can act on.

    pymysql surfaces the server's raw text -- "Access denied for user
    'x'@'172.17.0.1'" -- which says what happened but not what to do, and the
    two commonest causes under Docker are invisible from it: a grant that
    doesn't cover the container's source address, and a pre-existing volume
    that made MariaDB skip creating the user at all.
    """
    raw = str(exc)
    code = exc.args[0] if getattr(exc, "args", None) and isinstance(exc.args[0], int) else None
    nl = "\n"

    if code == 1045:                                   # bad credentials / no grant
        m = re.search(r"'([^']*)'@'([^']*)'", raw)
        user, from_host = (m.group(1), m.group(2)) if m else ("", "")
        u = user or "itvault"
        tips = []
        if from_host and re.match(r"^(172\.(1[6-9]|2\d|3[01])\.|10\.|192\.168\.)", from_host):
            tips.append(
                "MariaDB sees this login arriving from " + from_host + " -- Docker's address, "
                "not localhost -- and a MariaDB user is per-host. Grant it for that range:" + nl
                + "    CREATE USER '" + u + "'@'%' IDENTIFIED BY '<password>';" + nl
                + "    GRANT ALL PRIVILEGES ON <database>.* TO '" + u + "'@'%';" + nl
                + "    FLUSH PRIVILEGES;")
        tips.append(
            "If the database runs in a container you re-created over an EXISTING volume, "
            "MariaDB skipped its own setup and kept the old password -- the MARIADB_USER / "
            "MARIADB_PASSWORD you passed were ignored. Those only apply to a brand-new volume.")
        return ("Wrong username or password, or that user is not allowed to connect from here."
                + nl + nl + (nl + nl).join(tips))

    if code == 2003:                                   # connection refused
        return ("Nothing is listening on " + (host or "that host") + ":3306 yet." + nl + nl
                + "A database container needs 10-20 seconds to initialise before it accepts "
                "connections -- if you have just started it, wait and try again." + nl + nl
                + "Otherwise check the host: from inside this container 127.0.0.1 means the "
                "container itself. Use the database container's name on a shared Docker "
                "network, or host.docker.internal for a database on the Docker host.")

    if code == 2005:                                   # name does not resolve
        return ("The name '" + host + "' does not resolve from inside this container." + nl + nl
                + "Container names only resolve on a user-defined Docker network, so both "
                "containers have to share one. For a database on the Docker host, use "
                "host.docker.internal instead.")

    if code == 1049:                                   # no such database
        return ("That database does not exist yet. Create it, then try again:" + nl
                + "    CREATE DATABASE <name> CHARACTER SET utf8mb4;")

    if code == 1044:                                   # connected, no rights
        return ("The user connected, but has no rights on that database:" + nl
                + "    GRANT ALL PRIVILEGES ON <database>.* TO '<user>'@'%';" + nl
                + "    FLUSH PRIVILEGES;")

    return raw


def _module_write_allowed(module):
    """For routes that combine GET (read) with POST/PUT/DELETE (write) under
    one decorator -- call this inside the view for the write branches."""
    urole = session.get("role")
    if not session.get("user"):
        row = _resolve_session_from_api_key()
        if not row:
            return False
        urole = row["role"]
    if urole == ROLE_ADMIN:
        return True
    return _PERM_ORDER.get(_role_perms(urole).get(module, "none"), 0) >= _PERM_ORDER["write"]

# ---------- granular permissions ----------
# A role's five module levels (none/read/write) are coarse: "write on assets"
# also means import, export, delete and the trash. This catalogue breaks each
# module into the individual things a person can actually do, so a role can be
# given one of them and nothing else.
#
# Each leaf declares the module it belongs to and the level it implies, and the
# module columns on Roles are DERIVED from the granted leaves when a role is
# saved. Every existing module+level check therefore keeps working untouched --
# the leaves refine what a module already allows, they never reach past it.
#
# "admin_only" leaves are the ones a coarse module level never granted in the
# first place (the audit log, the network scan, backup/restore). They stay
# refused unless explicitly granted to a role, and they are enforced with
# _feature_allowed() at the route rather than by a module level.
FEATURE_GROUPS = [
    {"key": "assets", "label": "Assets", "module": "assets", "items": [
        ("assets.view",     "View assets",                  "read"),
        ("assets.create",   "Add an asset",                  "write"),
        ("assets.edit",     "Edit an asset",                 "write"),
        ("assets.delete",   "Delete an asset",               "write"),
        ("assets.checkout", "Check out / check in",          "write"),
        ("assets.import",   "Import from Excel",             "write"),
        ("assets.export",   "Export to Excel",               "read"),
        ("assets.labels",   "Print QR labels",               "read"),
        ("assets.catalog",  "Product catalog",               "read"),
        ("assets.trash",    "Trash (restore / purge)",       "write"),
    ]},
    {"key": "contracts", "label": "Contracts", "module": "contracts", "items": [
        ("contracts.view",   "View contracts",               "read"),
        ("contracts.create", "Add a contract",               "write"),
        ("contracts.edit",   "Edit a contract",              "write"),
        ("contracts.delete", "Delete a contract",            "write"),
        ("contracts.print",  "Print / export",               "read"),
    ]},
    {"key": "directory", "label": "Directory (Employees)", "module": "directory", "items": [
        ("directory.view",     "View employees",             "read"),
        ("directory.create",   "Add an employee",            "write"),
        ("directory.edit",     "Edit an employee",           "write"),
        ("directory.delete",   "Delete an employee",         "write"),
        ("directory.ldap",     "Sync from Active Directory", "write"),
        ("directory.reflists", "Departments / designations / locations", "admin_only"),
    ]},
    {"key": "tickets", "label": "Tickets", "module": "tickets", "items": [
        ("tickets.view",   "View tickets",                   "read"),
        ("tickets.create", "Raise a ticket",                 "write"),
        ("tickets.reply",  "Reply to a ticket",              "write"),
        ("tickets.queue",  "Set status, priority, assignee", "write"),
        ("tickets.edit",   "Edit a ticket's details",        "admin_only"),
        ("tickets.photos", "Add photos",                     "write"),
        ("tickets.delete", "Delete a ticket",                "admin_only"),
    ]},
    {"key": "settings", "label": "Settings", "module": "settings", "items": [
        ("settings.general",  "General (name, language, currency)", "write"),
        ("settings.branding", "Branding (logo, letterhead, theme)", "write"),
        ("settings.email",    "Email / SMTP",                "write"),
        ("settings.sla",      "Ticket SLAs and automation",   "write"),
        ("settings.labels",   "QR labels",                    "write"),
        ("settings.ldap",     "LDAP / Active Directory",      "write"),
        ("settings.unifi",    "UniFi",                        "write"),
        ("settings.portal",   "Support portal",               "write"),
    ]},
    {"key": "tools", "label": "Tools and records", "module": None, "items": [
        ("tools.scan",    "Network scan",                     "admin_only"),
        ("tools.audit",   "Audit log",                        "admin_only"),
        ("tools.backup",  "Backup and restore",               "admin_only"),
        ("tools.monitor", "Monitor screen",                   "admin_only"),
    ]},
]

# Reaches outside the module levels that the built-in roles already have
# today, so moving these routes onto feature checks takes nothing away from
# them. read-write can scan the network, read the audit log and open the
# monitor; both built-ins can open the monitor; backup/restore stays admin.
BUILTIN_EXTRA_FEATURES = {
    ROLE_EDIT: {"tools.scan", "tools.audit", "tools.monitor",
                "directory.reflists", "assets.import"},
    ROLE_VIEW: {"tools.monitor"},
}

# flat lookups
FEATURE_LEVEL = {k: lvl for g in FEATURE_GROUPS for (k, _lbl, lvl) in g["items"]}
FEATURE_MODULE = {k: g["module"] for g in FEATURE_GROUPS for (k, _l, _v) in g["items"]}
ALL_FEATURES = list(FEATURE_LEVEL.keys())


def _features_from_modules(perms):
    """Everything a role with these module levels could already do.

    Used for the built-in roles and for a custom role saved before this
    catalogue existed, so nobody loses access on upgrade. admin_only leaves
    are never included -- a module level never granted them.
    """
    out = set()
    for key, lvl in FEATURE_LEVEL.items():
        if lvl == "admin_only":
            continue
        mod = FEATURE_MODULE.get(key)
        have = (perms or {}).get(mod, "none")
        if _PERM_ORDER.get(have, 0) >= _PERM_ORDER.get(lvl, 2):
            out.add(key)
    return out


def _modules_from_features(granted):
    """Derive the five module levels from a set of granted leaves.

    A module is 'write' if any write-level leaf under it is granted, 'read' if
    only read-level ones are, 'none' if none are. This keeps the coarse
    columns -- which every existing route check reads -- in step with the
    leaves an admin actually ticked.
    """
    perms = {"assets": "none", "contracts": "none", "directory": "none",
             "tickets": "none", "settings": "none"}
    for key in granted:
        mod = FEATURE_MODULE.get(key)
        lvl = FEATURE_LEVEL.get(key)
        if mod not in perms or lvl not in ("read", "write"):
            continue
        if lvl == "write":
            perms[mod] = "write"
        elif perms[mod] == "none":
            perms[mod] = "read"
    return perms


def _role_features(role_name):
    """The set of feature keys a role may use."""
    if role_name == ROLE_ADMIN:
        return set(ALL_FEATURES)
    if role_name in BUILTIN_ROLE_PERMS:
        return (_features_from_modules(BUILTIN_ROLE_PERMS[role_name])
                | BUILTIN_EXTRA_FEATURES.get(role_name, set()))
    try:
        c = conn(); cur = c.cursor()
        cur.execute("SELECT perm_assets, perm_contracts, perm_directory, perm_tickets, "
                    "perm_settings, perms_json FROM Roles WHERE name=%s", [role_name])
        r = cur.fetchone(); c.close()
    except Exception:
        return set()
    if not r:
        return set()
    raw = r.get("perms_json")
    if raw:
        try:
            stored = json.loads(raw)
            if isinstance(stored, dict):
                return {k for k, v in stored.items() if v and k in FEATURE_LEVEL}
            if isinstance(stored, list):
                return {k for k in stored if k in FEATURE_LEVEL}
        except Exception:
            pass
    # saved before the catalogue existed -- fall back to what its module
    # levels already allowed, so the upgrade takes nothing away
    return _features_from_modules({
        "assets": r.get("perm_assets") or "none", "contracts": r.get("perm_contracts") or "none",
        "directory": r.get("perm_directory") or "none", "tickets": r.get("perm_tickets") or "none",
        "settings": r.get("perm_settings") or "none"})


def feature_required(key):
    """Gate a route on one catalogue leaf.

    Used for the things a module level never expressed -- the network scan,
    the audit log, backup/restore -- which were previously pinned to the
    built-in roles and so unreachable by any custom role however it was
    configured.
    """
    from functools import wraps
    def deco(f):
        @wraps(f)
        def wrap(*a, **k):
            if not session.get("user") and not _resolve_session_from_api_key():
                return jsonify({"error": "unauthorized"}), 401
            if not _feature_allowed(key):
                return jsonify({"error": "No access"}), 403
            return f(*a, **k)
        return wrap
    return deco


def _feature_allowed(key):
    """Can the current caller do this one thing? Mirrors
    _module_write_allowed()'s session-or-API-key resolution, so it holds for
    the mobile app too."""
    urole = session.get("role")
    if not session.get("user"):
        row = _resolve_session_from_api_key()
        if not row:
            return False
        urole = row["role"]
    if urole == ROLE_ADMIN:
        return True
    return key in _role_features(urole)


app = Flask(__name__, static_folder=None)
app.secret_key = SECRET
# Flask's session lifetime is a single app-wide value, so it can't express
# "5 minutes for this user, until-logout for that one". Mutating it per
# request would race across waitress' worker threads. Instead the COOKIE is
# allowed to live a long time, and the real timeout is an absolute expiry
# stamped into the session itself and enforced in _enforce_session_timeout()
# below -- absent for "keep me signed in", which then lasts until logout.
SHORT_SESSION_SECONDS = 5 * 60
app.permanent_session_lifetime = timedelta(days=30)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# UniFi Controller integration -- cached device/client snapshot (see _unifi_refresh)
_unifi_cache = {"ts": 0, "devices": [], "clients": [], "error": None}
_UNIFI_CACHE_TTL = 20

@app.teardown_request
def _release_db_connections(exc):
    """Give every pooled connection back at the end of the request.

    A query that raises -- a socket timeout above all -- used to leave the
    connection checked out mid-transaction, so whatever row it had written
    stayed locked. The next request touching that row then blocked until it
    timed out as well, and one slow write turned into every later write
    failing. Rolling back on the way out keeps a failure with the request
    that caused it.

    Views that close their own connection are unaffected: PooledDB's close()
    is a no-op once the connection has been returned.
    """
    conns = None
    try:
        conns = g.pop("_db_conns", None)
    except Exception:
        return
    for c in conns or []:
        if exc is not None:
            try: c.rollback()
            except Exception: pass
        try: c.close()
        except Exception: pass


@app.after_request
def _no_cache(resp):
    # Prevent stale JS/HTML caching so dashboard always re-renders fresh
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp

# ---------- password hashing (salted sha256) ----------
def hash_pw(pw, salt=None):
    if salt is None:
        salt = secrets.token_hex(8)
    return salt + "$" + hashlib.sha256((salt + pw).encode()).hexdigest()

def verify_pw(pw, stored):
    if not stored or "$" not in stored:
        return False
    salt, h = stored.split("$", 1)
    return h == hashlib.sha256((salt + pw).encode()).hexdigest()

# ---------- db ----------
# Opening a fresh MariaDB connection costs ~33ms (TCP + auth handshake);
# the query it then carries costs ~0.2ms. Since every request opened one or
# two, that handshake -- not the SQL -- was the floor under every endpoint's
# response time. Connections now come from a pool: conn() keeps its exact
# old signature and .close() hands the connection back instead of dropping
# it, so all ~130 call sites (including ones that nest a second conn()
# inside a handler that already holds one) work unchanged.
_pool_obj = None
_pool_key = None
_pool_lock = threading.Lock()

def _db_pool():
    """Pool for the CURRENT DB config. save_db_config() can repoint the app
    at a different server at runtime, so the pool is keyed on the config and
    rebuilt if it changes -- otherwise it would keep serving connections to
    the old database."""
    global _pool_obj, _pool_key
    key = (DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS)
    with _pool_lock:
        if _pool_obj is None or _pool_key != key:
            old = _pool_obj
            _pool_obj = PooledDB(
                creator=pymysql, host=DB_HOST, port=DB_PORT, user=DB_USER,
                password=DB_PASS, database=DB_NAME, charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
                # PyMySQL defaults read_timeout/write_timeout to None, i.e.
                # a stalled socket blocks that worker thread FOREVER. With
                # blocking=True below, hung threads keep their connections,
                # every later request queues behind them, and the whole app
                # stops responding -- which is what Windows was detecting as
                # an application hang and force-closing after a few hours.
                # Bounded waits let a stuck query fail its own request and
                # release the connection instead of taking the server down.
                connect_timeout=10,
                read_timeout=DB_TIMEOUT,
                write_timeout=DB_TIMEOUT,
                mincached=0,          # lazy: build connections on demand, so constructing the
                                      # pool itself can't fail (a bad repoint via the DB-settings
                                      # UI then surfaces per-request and recovers once fixed,
                                      # instead of erroring while the pool is being built)
                maxcached=8,          # ...and once warm, connections are reused from here
                maxconnections=32,    # ceiling; blocking=True queues rather than erroring past it
                blocking=True,
                ping=1,               # verify on checkout, so a connection MySQL closed
                                      # out from under us (wait_timeout) reconnects instead
                                      # of surfacing as a random query error
            )
            _pool_key = key
            if old is not None:
                try: old.close()
                except Exception: pass
        return _pool_obj

def conn():
    c = _db_pool().connection()
    # Remembered for the request teardown below. A view that raises before its
    # own c.close() would otherwise hand the connection back to nobody, with
    # its transaction still open and the rows it touched still locked.
    if has_request_context():
        try:
            g.setdefault("_db_conns", []).append(c)
        except Exception:
            pass
    return c

def init_db():
    c = conn(); cur = c.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS Assets (
        _id VARCHAR(40) PRIMARY KEY,
        AssetTag VARCHAR(40) DEFAULT '',
        Name VARCHAR(255), Type VARCHAR(255), Serial VARCHAR(255), Location VARCHAR(255),
        Status VARCHAR(255), ReceivedBy VARCHAR(255), NotesReceived TEXT, Notes TEXT, Note TEXT, PurchaseDate VARCHAR(255),
        WarrantyMonths INT DEFAULT 12, InvoiceFile VARCHAR(255), SignatureData TEXT,
        EmployeeName VARCHAR(255), EmployeeID VARCHAR(255), RequestedBy VARCHAR(255) DEFAULT '', Designation VARCHAR(255), Department VARCHAR(255), Email VARCHAR(255),
        Manufacturer VARCHAR(255), Model VARCHAR(255), is_deleted TINYINT DEFAULT 0,
        created_at DATETIME NULL
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS Manufacturers (
        id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(160) UNIQUE
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS Models (
        id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(160), manufacturer_id INT,
        UNIQUE KEY uq_mod (name, manufacturer_id)
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS Categories (
        id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(160) UNIQUE
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS ContractTypes (
        id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(160) UNIQUE
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS Departments (
        id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(160) UNIQUE
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS Designations (
        id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(160) UNIQUE
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS History (
        id INT AUTO_INCREMENT PRIMARY KEY, asset_id VARCHAR(40), ts DATETIME, user VARCHAR(80),
        field VARCHAR(80), old_val TEXT, new_val TEXT,
        INDEX idx_hist (asset_id)
    )""")
    # Per-ticket field trail, the same shape as History above so the ticket
    # view can show "who changed what, when" exactly like an asset does.
    cur.execute("""CREATE TABLE IF NOT EXISTS TicketHistory (
        id INT AUTO_INCREMENT PRIMARY KEY, ticket_id INT, ts DATETIME, user VARCHAR(80),
        field VARCHAR(80), old_val TEXT, new_val TEXT,
        INDEX idx_tkhist (ticket_id)
    )""")
    # GLPI-style: Contracts (warranty/vendor) and Locations (site tree)
    cur.execute("""CREATE TABLE IF NOT EXISTS Contracts (
        id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(200), vendor VARCHAR(160),
        type VARCHAR(120), start_date VARCHAR(40), end_date VARCHAR(40),
        cost DECIMAL(12,2) DEFAULT 0, asset_id VARCHAR(40), note TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS Locations (
        id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(160) UNIQUE, parent_id INT DEFAULT 0
    )""")
    # osTicket-style: Tickets + threaded replies
    cur.execute("""CREATE TABLE IF NOT EXISTS Tickets (
        id INT AUTO_INCREMENT PRIMARY KEY, code VARCHAR(20) UNIQUE,
        subject VARCHAR(255), description TEXT, priority VARCHAR(20) DEFAULT 'Normal',
        status VARCHAR(30) DEFAULT 'Open', requester VARCHAR(120), requester_email VARCHAR(160),
        assignee VARCHAR(80), asset_id VARCHAR(40), due_date VARCHAR(40), sla_hours INT DEFAULT 24,
        source VARCHAR(40) DEFAULT 'Web', created_by VARCHAR(80), created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP, closed_at DATETIME
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS TicketReplies (
        id INT AUTO_INCREMENT PRIMARY KEY, ticket_id INT, author VARCHAR(80), author_role VARCHAR(20),
        body TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_tk (ticket_id)
    )""")
    # Photos a requester attaches to a ticket. The bytes live in the database
    # rather than on disk: a container replaced by "docker pull" takes its
    # writable layer with it, and losing the photo of a broken screen along
    # with it is exactly the class of bug that moved branding in here too.
    cur.execute("""CREATE TABLE IF NOT EXISTS TicketAttachments (
        id INT AUTO_INCREMENT PRIMARY KEY, ticket_id INT,
        filename VARCHAR(255), mimetype VARCHAR(60), size INT DEFAULT 0,
        uploaded_by VARCHAR(80), created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        data MEDIUMBLOB,
        INDEX idx_tkatt (ticket_id)
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS Users (
        username VARCHAR(50) PRIMARY KEY,
        password VARCHAR(100),
        role VARCHAR(50),
        display VARCHAR(80),
        email VARCHAR(160)
    )""")
    # Custom roles: admins can build their own (e.g. "Manager") with per-module
    # read/write/none permissions, instead of only the 3 built-in tiers.
    cur.execute("""CREATE TABLE IF NOT EXISTS Roles (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(50) UNIQUE,
        perm_assets VARCHAR(10) DEFAULT 'none',
        perm_contracts VARCHAR(10) DEFAULT 'none',
        perm_directory VARCHAR(10) DEFAULT 'none',
        perm_tickets VARCHAR(10) DEFAULT 'none',
        perm_settings VARCHAR(10) DEFAULT 'none'
    )""")
    # migrate: perm_settings on an existing Roles table (CREATE TABLE IF NOT
    # EXISTS above does nothing once the table is there)
    try:
        cur.execute("SELECT perm_settings FROM Roles LIMIT 1")
    except Exception:
        try: cur.execute("ALTER TABLE Roles ADD COLUMN perm_settings VARCHAR(10) DEFAULT 'none'")
        except Exception: pass
    # migrate: per-feature grants (see FEATURE_GROUPS). A role saved before
    # this column existed leaves it NULL, and _role_features() then derives
    # its leaves from the module columns, so the upgrade takes nothing away.
    try:
        cur.execute("SELECT perms_json FROM Roles LIMIT 1")
    except Exception:
        try: cur.execute("ALTER TABLE Roles ADD COLUMN perms_json TEXT")
        except Exception: pass
    cur.execute("""CREATE TABLE IF NOT EXISTS Employees (
        _id VARCHAR(40) PRIMARY KEY,
        EmployeeID VARCHAR(255),
        EmployeeName VARCHAR(255),
        Designation VARCHAR(255),
        Department VARCHAR(255),
        Email VARCHAR(255),
        source VARCHAR(40) DEFAULT 'manual'
    )""")
    # migrate: add email column if an older schema exists
    try:
        cur.execute("SELECT email FROM Users LIMIT 1")
    except Exception:
        cur.execute("ALTER TABLE Users ADD COLUMN email VARCHAR(160)")
    # migrate: add 2FA columns (TOTP authenticator app + email OTP, both opt-in per user)
    for col, typ in [("totp_secret", "VARCHAR(64) DEFAULT ''"), ("totp_enabled", "TINYINT DEFAULT 0"),
                      ("email_otp_enabled", "TINYINT DEFAULT 0")]:
        try:
            cur.execute(f"SELECT {col} FROM Users LIMIT 1")
        except Exception:
            cur.execute(f"ALTER TABLE Users ADD COLUMN {col} {typ}")
    cur.execute("""CREATE TABLE IF NOT EXISTS Settings (
        id INT PRIMARY KEY DEFAULT 1,
        theme VARCHAR(10) DEFAULT 'dark',
        smtp_host VARCHAR(160),
        smtp_port INT DEFAULT 587,
        smtp_user VARCHAR(160),
        smtp_pass VARCHAR(160),
        smtp_from VARCHAR(160),
        notify_new BOOLEAN DEFAULT 1,
        notify_delete BOOLEAN DEFAULT 1,
        app_name VARCHAR(60) DEFAULT 'IT-Vault',
        logo_text VARCHAR(40) DEFAULT 'IT-Vault',
        matrix_on BOOLEAN DEFAULT 1,
        ldap_server VARCHAR(255),
        ldap_domain VARCHAR(255),
        ldap_bind_user VARCHAR(255),
        ldap_bind_pass VARCHAR(255),
        ldap_base_dn VARCHAR(255),
        qr_size INT DEFAULT 160,
        qr_fields VARCHAR(255) DEFAULT 'Name,AssetID,Type,Serial,Status,Location',
        label_size VARCHAR(20) DEFAULT '50.8x50.8',
        label_logo BOOLEAN DEFAULT 1,
        org_contact VARCHAR(60) DEFAULT ''
    )""")
    # migrate: add new columns if an older schema exists
    try:
        cur.execute("SELECT app_name FROM Settings LIMIT 1")
    except Exception:
        for col, typ in [("app_name","VARCHAR(60) DEFAULT 'IT-Vault'"),("logo_text","VARCHAR(40) DEFAULT 'IT-Vault'"),("matrix_on","BOOLEAN DEFAULT 1")]:
            try: cur.execute(f"ALTER TABLE Settings ADD COLUMN {col} {typ}")
            except Exception: pass
    # migrate: these columns were created under an older product name, which
    # stayed baked in as their MySQL-level DEFAULT forever after -- changing
    # the CREATE TABLE text above does nothing to an already-existing column,
    # so a Settings reset (factory wipe, or a fresh row insert) kept silently
    # reintroducing the old branding. Force the default straight.
    for col in ("app_name", "logo_text"):
        try: cur.execute(f"ALTER TABLE Settings ALTER COLUMN {col} SET DEFAULT 'IT-Vault'")
        except Exception: pass
    # migrate: add ldap settings columns if missing
    for col, typ in [("ldap_server","VARCHAR(255)"),("ldap_domain","VARCHAR(255)"),("ldap_bind_user","VARCHAR(255)"),("ldap_bind_pass","VARCHAR(255)"),("ldap_base_dn","VARCHAR(255)")]:
        try:
            cur.execute(f"SELECT {col} FROM Settings LIMIT 1")
        except Exception:
            cur.execute(f"ALTER TABLE Settings ADD COLUMN {col} {typ}")
    # migrate: add QR settings columns if missing
    for col, typ in [("qr_size","INT DEFAULT 160"),("qr_fields","VARCHAR(255) DEFAULT 'Name,AssetID,Type,Serial,Status,Location'"),("label_size","VARCHAR(20) DEFAULT '50.8x50.8'"),("label_logo","BOOLEAN DEFAULT 1"),("org_contact","VARCHAR(60) DEFAULT ''")]:
        try:
            cur.execute(f"SELECT {col} FROM Settings LIMIT 1")
        except Exception:
            try: cur.execute(f"ALTER TABLE Settings ADD COLUMN {col} {typ}")
            except Exception: pass
    try:
        cur.execute("SELECT email FROM Users LIMIT 1")
    except Exception:
        cur.execute("ALTER TABLE Users ADD COLUMN email VARCHAR(160)")
    # migrate: add portal_token to Settings if missing
    try:
        cur.execute("SELECT portal_token FROM Settings LIMIT 1")
    except Exception:
        try: cur.execute("ALTER TABLE Settings ADD COLUMN portal_token VARCHAR(64) DEFAULT ''")
        except Exception: pass
    # migrate: add WarrantyMonths to Assets if missing
    try:
        cur.execute("SELECT WarrantyMonths FROM Assets LIMIT 1")
    except Exception:
        cur.execute("ALTER TABLE Assets ADD COLUMN WarrantyMonths INT DEFAULT 12")
    # migrate: add InvoiceFile to Assets if missing
    try:
        cur.execute("SELECT InvoiceFile FROM Assets LIMIT 1")
    except Exception:
        cur.execute("ALTER TABLE Assets ADD COLUMN InvoiceFile VARCHAR(255)")
    # migrate: add AssetTag (human-friendly "IT-1001" style ID, editable) and backfill existing rows
    try:
        cur.execute("SELECT AssetTag FROM Assets LIMIT 1")
    except Exception:
        cur.execute("ALTER TABLE Assets ADD COLUMN AssetTag VARCHAR(40) DEFAULT ''")
    try:
        cur.execute("SELECT _id FROM Assets WHERE AssetTag IS NULL OR AssetTag='' ORDER BY created_at IS NULL, created_at, _id")
        missing = cur.fetchall()
        if missing:
            cur.execute("SELECT MAX(CAST(SUBSTRING(AssetTag,4) AS UNSIGNED)) AS n FROM Assets WHERE AssetTag REGEXP '^IT-[0-9]+$'")
            n = (cur.fetchone() or {}).get("n") or 1000
            for r in missing:
                n += 1
                cur.execute("UPDATE Assets SET AssetTag=%s WHERE _id=%s", [f"IT-{n}", r["_id"]])
    except Exception:
        pass
    # migrate: add GLPI-style columns (Manufacturer, Model, is_deleted)
    try:
        cur.execute("SELECT is_deleted FROM Assets LIMIT 1")
    except Exception:
        for col, typ in [("Manufacturer","VARCHAR(255)"),("Model","VARCHAR(255)"),("is_deleted","TINYINT DEFAULT 0")]:
            try: cur.execute(f"ALTER TABLE Assets ADD COLUMN {col} {typ}")
            except Exception: pass
    # migrate: add created_at so "recent assets" can be ordered by time, not name
    try:
        cur.execute("SELECT created_at FROM Assets LIMIT 1")
    except Exception:
        try: cur.execute("ALTER TABLE Assets ADD COLUMN created_at DATETIME NULL")
        except Exception: pass
    # migrate: add Note to Assets if missing
    try:
        cur.execute("SELECT Note FROM Assets LIMIT 1")
    except Exception:
        cur.execute("ALTER TABLE Assets ADD COLUMN Note TEXT")
    # migrate: add SignatureData to Assets if missing
    try:
        cur.execute("SELECT SignatureData FROM Assets LIMIT 1")
    except Exception:
        cur.execute("ALTER TABLE Assets ADD COLUMN SignatureData TEXT")
    # migrate: add SLA policy columns to Settings if missing
    for col, typ in [("sla_low","INT DEFAULT 72"),("sla_normal","INT DEFAULT 24"),("sla_high","INT DEFAULT 8"),("sla_urgent","INT DEFAULT 4"),("sla_breach_notify","BOOLEAN DEFAULT 1"),("auto_assign_roundrobin","BOOLEAN DEFAULT 0"),("notify_on_create","BOOLEAN DEFAULT 1"),("notify_on_resolve","BOOLEAN DEFAULT 1"),("notify_on_reply","BOOLEAN DEFAULT 1")]:
        try:
            cur.execute(f"SELECT {col} FROM Settings LIMIT 1")
        except Exception:
            try: cur.execute(f"ALTER TABLE Settings ADD COLUMN {col} {typ}")
            except Exception: pass
    # migrate: add category column to Tickets if missing
    try:
        cur.execute("SELECT category FROM Tickets LIMIT 1")
    except Exception:
        try: cur.execute("ALTER TABLE Tickets ADD COLUMN category VARCHAR(80) DEFAULT ''")
        except Exception: pass
    # create Employees directory table if missing
    cur.execute("""CREATE TABLE IF NOT EXISTS Employees (
        _id VARCHAR(40) PRIMARY KEY,
        EmployeeID VARCHAR(255),
        EmployeeName VARCHAR(255),
        Designation VARCHAR(255),
        Department VARCHAR(255),
        Email VARCHAR(255),
        source VARCHAR(40) DEFAULT 'manual'
    )""")
    # new ITAM tables
    cur.execute("""CREATE TABLE IF NOT EXISTS Checkouts (
        id INT AUTO_INCREMENT PRIMARY KEY,
        asset_id VARCHAR(40),
        username VARCHAR(50),
        checkout_date VARCHAR(30),
        expected_checkin VARCHAR(30),
        checkin_date VARCHAR(30),
        note TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS Maintenance (
        id INT AUTO_INCREMENT PRIMARY KEY,
        asset_id VARCHAR(40),
        date VARCHAR(30),
        mtype VARCHAR(80),
        cost DECIMAL(12,2) DEFAULT 0,
        note TEXT,
        by_user VARCHAR(50)
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS AuditLog (
        id INT AUTO_INCREMENT PRIMARY KEY,
        ts DATETIME DEFAULT CURRENT_TIMESTAMP,
        actor VARCHAR(50),
        action VARCHAR(60),
        asset_id VARCHAR(40),
        detail TEXT
    )""")
    cur.execute("SELECT COUNT(*) AS n FROM Settings")
    if cur.fetchone()["n"] == 0:
        cur.execute("INSERT INTO Settings (id, theme) VALUES (1, 'dark')")
    if not os.path.exists(LOGO_PATH):
        open(LOGO_PATH, "wb").close()  # placeholder
    # Seed the first admin ONLY for an unattended install, i.e. one where the
    # password was supplied deliberately via the environment. Seeding
    # unconditionally meant a restart after a factory reset quietly recreated
    # the schema AND a well-known default account, skipping the setup wizard
    # entirely -- undoing the reset and leaving admin/admin123 valid. With no
    # env password, Users stays empty so setup_needed() stays true and the
    # wizard asks for credentials instead.
    cur.execute("SELECT COUNT(*) AS n FROM Users")
    if cur.fetchone()["n"] == 0:
        if _env("ITVAULT_ADMIN_PASS", "ITGUY_ADMIN_PASS"):
            cur.execute("INSERT INTO Users (username, password, role, display, email) VALUES (%s,%s,%s,%s,%s)",
                        (ADMIN_USER, hash_pw(ADMIN_PASS), ROLE_ADMIN, "Administrator", ""))
        else:
            print("[itvault] no users and no ITVAULT_ADMIN_PASS set -- "
                  "first-run setup wizard will create the admin", flush=True)
    c.commit(); c.close()

def migrate_schema():
    """Add new columns for the Customization engine / Profile / User Settings without dropping data."""
    c = conn(); cur = c.cursor()
    # Settings: theme engine + i18n + region
    set_cols = {
        "theme_preset": "VARCHAR(20) DEFAULT 'deepdark'",
        "bg_type": "VARCHAR(12) DEFAULT 'solid'",
        "bg": "VARCHAR(40) DEFAULT '#0a0d13'",
        "comp_bg": "VARCHAR(40) DEFAULT '#121826'",
        "radius": "INT DEFAULT 12",
        "font": "VARCHAR(40) DEFAULT 'Rajdhani'",
        "accent": "VARCHAR(20) DEFAULT '#ff3b30'",
        "accent2": "VARCHAR(20) DEFAULT '#c0392b'",
        "language": "VARCHAR(10) DEFAULT 'en'",
        "currency": "VARCHAR(6) DEFAULT 'AED'",
        "region": "VARCHAR(40) DEFAULT 'UAE'",
    }
    for col, typ in set_cols.items():
        try:
            cur.execute(f"ALTER TABLE Settings ADD COLUMN {col} {typ}")
        except Exception:
            pass
    # migrate: accent/accent2 were added back when the default theme was blue
    # (#3b9eff/#7c5cff) -- ADD COLUMN above is a no-op once the column already
    # exists, so that old blue stayed the live MySQL-level default forever
    # after, the same way the old app_name default did. Force it to the
    # current red Deep Dark preset, and repair any row still on the old blue.
    try: cur.execute("ALTER TABLE Settings ALTER COLUMN accent SET DEFAULT '#ff3b30'")
    except Exception: pass
    try: cur.execute("ALTER TABLE Settings ALTER COLUMN accent2 SET DEFAULT '#c0392b'")
    except Exception: pass
    try: cur.execute("UPDATE Settings SET accent='#ff3b30' WHERE accent='#3b9eff'")
    except Exception: pass
    try: cur.execute("UPDATE Settings SET accent2='#c0392b' WHERE accent2='#7c5cff'")
    except Exception: pass
    # migrate: "Deep Dark" (THEME_PRESETS.deepdark in app.js) -- kept in sync
    # with the JS preset by hand each time it's tuned; now pure black on both
    # the page background and card surfaces, per explicit request. Column
    # default (and the live row, if it's still on an older shade) both get
    # corrected; font/radius were already right.
    try: cur.execute("ALTER TABLE Settings ALTER COLUMN bg SET DEFAULT '#000000'")
    except Exception: pass
    try: cur.execute("ALTER TABLE Settings ALTER COLUMN comp_bg SET DEFAULT '#000000'")
    except Exception: pass
    try: cur.execute("ALTER TABLE Settings ALTER COLUMN font SET DEFAULT 'Inter'")
    except Exception: pass
    try: cur.execute("UPDATE Settings SET bg='#000000' WHERE bg IN ('#0a0d13', '#05060a')")
    except Exception: pass
    try: cur.execute("UPDATE Settings SET comp_bg='#000000' WHERE comp_bg IN ('#121826', '#0c0f18')")
    except Exception: pass
    user_cols = {
        "avatar": "VARCHAR(60) DEFAULT ''",
        "api_key": "VARCHAR(64) DEFAULT ''",
        "last_login": "VARCHAR(40) DEFAULT ''",
    }
    for col, typ in user_cols.items():
        try:
            cur.execute(f"ALTER TABLE Users ADD COLUMN {col} {typ}")
        except Exception:
            pass
    # Assets: purchase price (formatted by selected currency)
    try:
        cur.execute("ALTER TABLE Assets ADD COLUMN Price DECIMAL(12,2) DEFAULT 0")
    except Exception:
        pass
    # Assets: MAC address (e.g. from network scan discovery)
    try:
        cur.execute("ALTER TABLE Assets ADD COLUMN MacAddress VARCHAR(64) DEFAULT ''")
    except Exception:
        pass
    # Assets: who requested the device, separate from EmployeeID (who it's
    # actually assigned/checked out to)
    try:
        cur.execute("ALTER TABLE Assets ADD COLUMN RequestedBy VARCHAR(255) DEFAULT ''")
    except Exception:
        pass
    # Contracts: who/where a contract belongs to (employee, location, department)
    contract_cols = {
        "employee_id": "VARCHAR(255) DEFAULT ''",
        "location": "VARCHAR(160) DEFAULT ''",
        "department": "VARCHAR(160) DEFAULT ''",
        "license_key": "VARCHAR(500) DEFAULT ''",
        "is_deleted": "TINYINT DEFAULT 0",
        "vendor_email": "VARCHAR(160) DEFAULT ''",
        "expiry_notified_at": "VARCHAR(40) DEFAULT ''",
        "billing_period": "VARCHAR(20) DEFAULT 'One-Time'",
        "contract_tag": "VARCHAR(40) DEFAULT ''",
    }
    for col, typ in contract_cols.items():
        try:
            cur.execute(f"ALTER TABLE Contracts ADD COLUMN {col} {typ}")
        except Exception:
            pass
    # UniFi Controller integration (Dashboard device/client widgets)
    unifi_cols = {
        "unifi_enabled": "BOOLEAN DEFAULT 0",
        "unifi_host": "VARCHAR(200) DEFAULT ''",
        "unifi_port": "INT DEFAULT 443",
        "unifi_site": "VARCHAR(80) DEFAULT 'default'",
        "unifi_user": "VARCHAR(120) DEFAULT ''",
        "unifi_pass": "VARCHAR(200) DEFAULT ''",
        "unifi_is_os": "BOOLEAN DEFAULT 1",
        "unifi_verify_ssl": "BOOLEAN DEFAULT 0",
    }
    for col, typ in unifi_cols.items():
        try:
            cur.execute(f"ALTER TABLE Settings ADD COLUMN {col} {typ}")
        except Exception:
            pass
    # Users.role needs room for custom role names, not just the 3 built-ins
    try:
        cur.execute("ALTER TABLE Users MODIFY COLUMN role VARCHAR(50)")
    except Exception:
        pass
    # Branding: organization contact details (shown on QR labels / print footers)
    # `logo` holds the uploaded logo's raw PNG bytes, embedded straight into
    # prints/PDFs. It was missing from every schema-creating path -- older
    # databases happened to carry it, so /api/me and the label code could
    # SELECT it without complaint, but any FRESH schema (a new install, or a
    # factory reset rebuilding from code) came up without the column and
    # failed with "Unknown column 'logo'" on the first request after setup.
    branding_cols = {
        "company_phone": "VARCHAR(60) DEFAULT ''",
        "company_address": "VARCHAR(255) DEFAULT ''",
        "has_letterhead": "TINYINT DEFAULT 0",
        "logo": "MEDIUMBLOB",
        "letterhead": "MEDIUMBLOB",
    }
    for col, typ in branding_cols.items():
        try:
            cur.execute(f"ALTER TABLE Settings ADD COLUMN {col} {typ}")
        except Exception:
            pass
    # Scheduled backups: frequency, scope, and how many old backups to retain
    backup_cols = {
        "backup_schedule": "VARCHAR(20) DEFAULT 'off'",
        "backup_scope": "VARCHAR(20) DEFAULT 'all'",
        "backup_retain": "INT DEFAULT 7",
        "backup_last_run": "VARCHAR(40) DEFAULT ''",
    }
    for col, typ in backup_cols.items():
        try:
            cur.execute(f"ALTER TABLE Settings ADD COLUMN {col} {typ}")
        except Exception:
            pass
    # Employees: real editable staff/HR ID, separate from EmployeeID (which
    # holds the AD/login username for LDAP-synced staff)
    try:
        cur.execute("ALTER TABLE Employees ADD COLUMN EmpCode VARCHAR(64) DEFAULT ''")
    except Exception:
        pass
    # Item Category picker: backfill from whatever Type values already exist
    # on real assets, so switching that field to a dropdown doesn't blank out
    # anyone's existing data (one-time -- skipped once Categories has rows)
    try:
        cur.execute("SELECT COUNT(*) AS n FROM Categories")
        if (cur.fetchone() or {}).get("n", 0) == 0:
            cur.execute("SELECT DISTINCT Type FROM Assets WHERE Type IS NOT NULL AND Type<>''")
            for r in cur.fetchall():
                t = (r.get("Type") or "").strip()
                if t:
                    cur.execute("INSERT IGNORE INTO Categories (name) VALUES (%s)", [t])
    except Exception:
        pass
    # Contract Type picker: seed with the original built-in options plus
    # whatever type values already exist on real contracts, so switching
    # that field to a managed dropdown doesn't blank out anyone's data
    try:
        cur.execute("SELECT COUNT(*) AS n FROM ContractTypes")
        if (cur.fetchone() or {}).get("n", 0) == 0:
            for t in ["AMC", "License", "Subscription", "Warranty", "Support", "Lease", "Other"]:
                cur.execute("INSERT IGNORE INTO ContractTypes (name) VALUES (%s)", [t])
            cur.execute("SELECT DISTINCT type FROM Contracts WHERE type IS NOT NULL AND type<>''")
            for r in cur.fetchall():
                t = (r.get("type") or "").strip()
                if t:
                    cur.execute("INSERT IGNORE INTO ContractTypes (name) VALUES (%s)", [t])
    except Exception:
        pass
    # Directory pickers (Department / Location / Designation): backfill from
    # whatever free-text values already exist on real employees/assets, so
    # switching those fields to dropdowns doesn't blank out anyone's data
    try:
        cur.execute("SELECT COUNT(*) AS n FROM Departments")
        if (cur.fetchone() or {}).get("n", 0) == 0:
            cur.execute("SELECT DISTINCT Department FROM Employees WHERE Department IS NOT NULL AND Department<>''")
            for r in cur.fetchall():
                d = (r.get("Department") or "").strip()
                if d:
                    cur.execute("INSERT IGNORE INTO Departments (name) VALUES (%s)", [d])
    except Exception:
        pass
    try:
        cur.execute("SELECT COUNT(*) AS n FROM Designations")
        if (cur.fetchone() or {}).get("n", 0) == 0:
            cur.execute("SELECT DISTINCT Designation FROM Employees WHERE Designation IS NOT NULL AND Designation<>''")
            for r in cur.fetchall():
                d = (r.get("Designation") or "").strip()
                if d:
                    cur.execute("INSERT IGNORE INTO Designations (name) VALUES (%s)", [d])
    except Exception:
        pass
    # Locations (existing GLPI site tree) doubles as the asset Location picker
    # -- keep it topped up with any free-text values already used on assets
    try:
        cur.execute("SELECT DISTINCT Location FROM Assets WHERE Location IS NOT NULL AND Location<>''")
        for r in cur.fetchall():
            l = (r.get("Location") or "").strip()
            if l:
                cur.execute("INSERT IGNORE INTO Locations (name, parent_id) VALUES (%s, 0)", [l])
    except Exception:
        pass
    # avatar column may be too small for base64 photos -> enlarge if needed
    try:
        cur.execute("SELECT avatar FROM Users LIMIT 1")
        cur.execute("ALTER TABLE Users MODIFY avatar MEDIUMTEXT")
    except Exception:
        try:
            cur.execute("ALTER TABLE Users ADD COLUMN avatar MEDIUMTEXT")
        except Exception:
            pass
    c.commit(); c.close()

def row_to_dict(row):
    return {"_id": row["_id"], "InvoiceFile": row.get("InvoiceFile", "") or "",
            "SignatureData": row.get("SignatureData", "") or "",
            **{col: row.get(col, "") for col in COLUMNS}}

def lan_base_url():
    """Return a LAN-reachable base URL (http://<this-host-ip>:5000/) so QR codes scan from any device."""
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80)); ip = s.getsockname()[0]; s.close()
    except Exception:
        ip = "127.0.0.1"
    return f"http://{ip}:5000/"

# ---------- auth ----------
def role_of():
    return session.get("role")

@app.route("/api/login", methods=["POST"])
def login():
    d = request.get_json(force=True, silent=True) or {}
    u = (d.get("username") or "").strip(); p = d.get("password", "")
    c = conn(); cur = c.cursor()
    cur.execute("SELECT username, password, role, display, email, totp_enabled, email_otp_enabled FROM Users WHERE username=%s", [u])
    row = cur.fetchone(); c.close()
    if row and verify_pw(p, row["password"]):
        methods = []
        if row.get("totp_enabled"): methods.append("totp")
        if row.get("email_otp_enabled"): methods.append("email")
        if methods:
            session.clear()
            session["pending_2fa_user"] = row["username"]; session["pending_2fa_role"] = row["role"]
            session["pending_2fa_display"] = row["display"]; session["pending_2fa_exp"] = time.time() + 300
            session["pending_2fa_remember"] = bool(d.get("remember"))
            session.permanent = True
            if "email" in methods:
                _send_login_otp_email(row["username"], row.get("email") or "")
            return jsonify({"ok": True, "need_2fa": True, "methods": methods})
        _start_session(row["username"], row["role"], row["display"], bool(d.get("remember")))
        return jsonify({"ok": True, "role": row["role"]})
    return jsonify({"ok": False, "error": "Invalid credentials"}), 401

def _pending_2fa_user():
    """Validates the short-lived pending-2FA session set by login() when a user has
    TOTP or email-OTP enabled. Returns the username, or None if there's no valid
    pending 2FA challenge (expired / never started)."""
    u = session.get("pending_2fa_user")
    if not u or time.time() > session.get("pending_2fa_exp", 0):
        return None
    return u

def _send_login_otp_email(username, to_email):
    if not to_email:
        return False
    code = f"{secrets.randbelow(1000000):06d}"
    session["pending_2fa_email_code"] = code
    session["pending_2fa_email_sent_at"] = time.time()
    import smtplib
    from email.message import EmailMessage
    c = conn(); cur = c.cursor()
    cur.execute("SELECT smtp_host, smtp_port, smtp_user, smtp_pass, smtp_from, app_name FROM Settings WHERE id=1")
    s = cur.fetchone() or {}; c.close()
    if not s.get("smtp_host"):
        return False
    try:
        bn = s.get("app_name") or "IT-Vault"
        msg = EmailMessage()
        msg["Subject"] = f"{bn}: your sign-in code is {code}"
        msg["From"] = s.get("smtp_from") or s.get("smtp_user")
        msg["To"] = to_email
        msg.set_content(f"Your {bn} sign-in verification code is: {code}\n\nThis code expires in 5 minutes. If you didn't request this, you can ignore this email." + _email_footer(bn))
        with smtplib.SMTP(s["smtp_host"], int(s.get("smtp_port", 587) or 587), timeout=10) as sv:
            if s.get("smtp_user"): sv.starttls(); sv.login(s["smtp_user"], s.get("smtp_pass", ""))
            sv.send_message(msg)
        return True
    except Exception as e:
        print("login OTP email error:", e); return False

@app.route("/api/2fa/resend-email-code", methods=["POST"])
def resend_login_otp():
    u = _pending_2fa_user()
    if not u: return jsonify({"error": "no pending sign-in"}), 400
    if time.time() - session.get("pending_2fa_email_sent_at", 0) < 20:
        return jsonify({"error": "please wait a few seconds before requesting another code"}), 429
    c = conn(); cur = c.cursor()
    cur.execute("SELECT email FROM Users WHERE username=%s", [u]); row = cur.fetchone() or {}; c.close()
    ok = _send_login_otp_email(u, row.get("email") or "")
    return jsonify({"ok": ok}) if ok else (jsonify({"error": "could not send email -- check SMTP settings"}), 400)

@app.route("/api/2fa/verify-login", methods=["POST"])
def verify_login_2fa():
    u = _pending_2fa_user()
    if not u: return jsonify({"ok": False, "error": "Sign-in expired -- please log in again"}), 400
    d = request.get_json(force=True, silent=True) or {}
    method = d.get("method"); code = (d.get("code") or "").strip()
    c = conn(); cur = c.cursor()
    cur.execute("SELECT username, role, display, totp_secret, totp_enabled, email_otp_enabled FROM Users WHERE username=%s", [u])
    row = cur.fetchone(); c.close()
    if not row: return jsonify({"ok": False, "error": "Sign-in expired -- please log in again"}), 400
    ok = False
    if method == "totp" and row.get("totp_enabled") and row.get("totp_secret"):
        ok = pyotp.TOTP(row["totp_secret"]).verify(code, valid_window=1)
    elif method == "email" and row.get("email_otp_enabled"):
        ok = bool(code) and code == session.get("pending_2fa_email_code")
    if not ok:
        return jsonify({"ok": False, "error": "Invalid or expired code"}), 401
    remember = bool(session.get("pending_2fa_remember"))
    for k in ("pending_2fa_user", "pending_2fa_role", "pending_2fa_display", "pending_2fa_exp",
              "pending_2fa_email_code", "pending_2fa_email_sent_at", "pending_2fa_remember"):
        session.pop(k, None)
    _start_session(row["username"], row["role"], row["display"], remember)
    return jsonify({"ok": True, "role": row["role"]})

def _send_password_reset_email(username, to_email, code):
    if not to_email:
        return False
    import smtplib
    from email.message import EmailMessage
    c = conn(); cur = c.cursor()
    cur.execute("SELECT smtp_host, smtp_port, smtp_user, smtp_pass, smtp_from, app_name FROM Settings WHERE id=1")
    s = cur.fetchone() or {}; c.close()
    if not s.get("smtp_host"):
        return False
    try:
        bn = s.get("app_name") or "IT-Vault"
        msg = EmailMessage()
        msg["Subject"] = f"{bn}: password reset code"
        msg["From"] = s.get("smtp_from") or s.get("smtp_user")
        msg["To"] = to_email
        msg.set_content(f"Your {bn} password reset code is: {code}\n\nThis code expires in 10 minutes. "
                         f"If you didn't request this, you can safely ignore this email -- your password "
                         f"will not be changed." + _email_footer(bn))
        with smtplib.SMTP(s["smtp_host"], int(s.get("smtp_port", 587) or 587), timeout=10) as sv:
            if s.get("smtp_user"): sv.starttls(); sv.login(s["smtp_user"], s.get("smtp_pass", ""))
            sv.send_message(msg)
        return True
    except Exception as e:
        print("password reset email error:", e); return False

@app.route("/api/forgot-password/request", methods=["POST"])
def forgot_password_request():
    """Step 1 of self-service password reset: emails a 6-digit code good for
    10 minutes. Always reports success regardless of whether the
    username/email matches an account, so this can't be used to enumerate
    valid logins."""
    d = request.get_json(force=True, silent=True) or {}
    ident = (d.get("username") or "").strip()
    if not ident:
        return jsonify({"error": "username or email required"}), 400
    if session.get("pwreset_sent_at") and time.time() - session["pwreset_sent_at"] < 20:
        return jsonify({"error": "please wait a few seconds before requesting another code"}), 429
    c = conn(); cur = c.cursor()
    cur.execute("SELECT username, email FROM Users WHERE username=%s OR email=%s", [ident, ident])
    row = cur.fetchone(); c.close()
    if row and row.get("email"):
        code = f"{secrets.randbelow(1000000):06d}"
        session.clear()
        session["pwreset_user"] = row["username"]
        session["pwreset_code"] = code
        session["pwreset_exp"] = time.time() + 600
        session["pwreset_sent_at"] = time.time()
        session.permanent = True
        _send_password_reset_email(row["username"], row["email"], code)
    return jsonify({"ok": True})

@app.route("/api/forgot-password/reset", methods=["POST"])
def forgot_password_reset():
    """Step 2: verify the emailed code and set a new password. Signs the user
    in on success, same as completing 2FA."""
    u = session.get("pwreset_user")
    if not u or time.time() > session.get("pwreset_exp", 0):
        return jsonify({"error": "Reset code expired -- please request a new one"}), 400
    d = request.get_json(force=True, silent=True) or {}
    code = (d.get("code") or "").strip()
    new_pw = d.get("new_password") or ""
    if not code or code != session.get("pwreset_code"):
        return jsonify({"error": "Invalid code"}), 401
    if not new_pw:
        return jsonify({"error": "New password required"}), 400
    c = conn(); cur = c.cursor()
    cur.execute("UPDATE Users SET password=%s WHERE username=%s", (hash_pw(new_pw), u))
    c.commit()
    cur.execute("SELECT username, role, display FROM Users WHERE username=%s", [u]); row = cur.fetchone(); c.close()
    for k in ("pwreset_user", "pwreset_code", "pwreset_exp", "pwreset_sent_at"):
        session.pop(k, None)
    if row:
        _start_session(row["username"], row["role"], row["display"], remember=False)
    audit(u, "PASSWORD_RESET", "", "password reset via email OTP")
    return jsonify({"ok": True})

@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear(); return jsonify({"ok": True})

@app.route("/api/me")
def me():
    if not session.get("user"):
        if not _resolve_session_from_api_key():
            return jsonify({"user": None})
    c = conn(); cur = c.cursor()
    cur.execute("SELECT display, email, avatar, api_key, last_login FROM Users WHERE username=%s", [session["user"]])
    row = cur.fetchone() or {}
    cur.execute("SELECT theme, ldap_server, ldap_domain, ldap_bind_user, ldap_base_dn, theme_preset, bg_type, bg, comp_bg, radius, font, accent, accent2, language, currency, region, matrix_on, app_name, logo_text, logo, has_letterhead FROM Settings WHERE id=1")
    s = cur.fetchone() or {"theme":"dark"}
    c.close()
    # The sidebar can only hide what it can't reach if it knows the actual
    # per-module rights, so send them with the identity rather than making the
    # UI infer access from the role name (which custom roles make impossible).
    return jsonify({"user": session["user"], "role": session["role"],
                    "perms": _role_perms(session["role"]),
                    "features": sorted(_role_features(session["role"])),
                    "display": row.get("display", ""), "email": row.get("email", ""),
                    "avatar": row.get("avatar", ""), "api_key": row.get("api_key", ""),
                    "last_login": row.get("last_login", ""),
                    "theme": s.get("theme", "dark"),
                    "theme_preset": s.get("theme_preset", "deepdark"), "bg_type": s.get("bg_type","solid"),
                    "bg": s.get("bg", "#0a0d13"), "comp_bg": s.get("comp_bg", "#121826"),
                    "radius": s.get("radius", 12), "font": s.get("font", "Rajdhani"),
                    "accent": s.get("accent", "#ff3b30"), "accent2": s.get("accent2", "#c0392b"),
                    "language": s.get("language", "en"), "currency": s.get("currency", "AED"),
                    "region": s.get("region", "UAE"), "matrix_on": s.get("matrix_on", 1),
                    "app_name": s.get("app_name", "IT-Vault"), "logo_text": s.get("logo_text", "IT-Vault"),
                    "logo": "/logo.png", "has_letterhead": bool(s.get("has_letterhead")),
                    "ldap_server": s.get("ldap_server", ""), "ldap_domain": s.get("ldap_domain", ""),
                    "ldap_bind_user": s.get("ldap_bind_user", ""), "ldap_base_dn": s.get("ldap_base_dn", "")})

def _user_from_api_key(key):
    """Resolve a persistent per-user API key (Settings > My Account) to its
    owner. Used so the native mobile client can stay logged in indefinitely
    (like Nextcloud's app passwords) instead of relying on the web UI's
    short-lived session cookie."""
    if not key:
        return None
    c = conn(); cur = c.cursor()
    cur.execute("SELECT username, role FROM Users WHERE api_key=%s AND api_key<>''", [key])
    row = cur.fetchone(); c.close()
    return row

def _request_api_key():
    """Look for a persistent API key on this request: an X-Api-Key header,
    an Authorization: Bearer header, or -- for the Android app's WebView,
    which just loads the real web UI and can't add custom headers to page
    navigations -- an itguy_api_key cookie set once at login."""
    key = request.headers.get("X-Api-Key")
    if not key:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            key = auth_header[7:]
    if not key:
        key = request.cookies.get("itguy_api_key")
    return (key or "").strip()

def _resolve_session_from_api_key():
    """If there's no active session cookie, try to establish one from a
    persistent API key so the rest of the request behaves as if logged in.
    Returns the resolved user row, or None."""
    row = _user_from_api_key(_request_api_key())
    if row:
        session["user"] = row["username"]
        session["role"] = row["role"]
    return row

def auth_required(role=None, module=None, level="write"):
    """role: legacy fixed-role gate (list of role names, e.g. [ROLE_ADMIN, ROLE_EDIT]).
    module/level: granular gate against a role's per-module permission (see
    _role_perms) -- lets a custom role (e.g. "Manager") get e.g. read-only on
    Assets and read-write on Directory. admin always passes module checks.
    Only one of role / module should be given; module wins if both are set."""
    from functools import wraps
    def deco(f):
        @wraps(f)
        def wrap(*a, **k):
            urole = session.get("role")
            if not session.get("user"):
                row = _resolve_session_from_api_key()
                if not row:
                    return jsonify({"error": "unauthorized"}), 401
                urole = row["role"]
            if module:
                if urole != ROLE_ADMIN:
                    have = _role_perms(urole).get(module, "none")
                    if _PERM_ORDER.get(have, 0) < _PERM_ORDER.get(level, 2):
                        return jsonify({"error": "No access"}), 403
            elif role and urole not in (role if isinstance(role, list) else [role]):
                return jsonify({"error": "No access"}), 403
            return f(*a, **k)
        return wrap
    return deco

def _ldap_settings():
    c = conn(); cur = c.cursor()
    cur.execute("SELECT ldap_server, ldap_domain, ldap_bind_user, ldap_bind_pass, ldap_base_dn FROM Settings WHERE id=1")
    row = cur.fetchone() or {}; c.close()
    return row

def _ldap_connect(row, get_info=ldap3.NONE):
    """Build & bind an ldap3 connection to a Windows DC. Robust URL/port handling."""
    import ssl
    server = (row.get("ldap_server") or "").strip()
    bind_user = (row.get("ldap_bind_user") or "").strip()
    bind_pass = (row.get("ldap_bind_pass") or "").strip()
    if not server or not bind_user or not bind_pass:
        raise ValueError("LDAP settings incomplete (need server, bind user, bind password)")
    s = server.lower()
    if not (s.startswith("ldap://") or s.startswith("ldaps://")):
        # bare host: default to ldaps if port 636 present else plain ldap
        if ":636" in s:
            s = "ldaps://" + server
        else:
            s = "ldap://" + server
    use_ssl = s.startswith("ldaps://")
    # Windows DCs usually have self-signed certs -> don't enforce cert validation
    tls_cfg = ldap3.Tls(validate=ssl.CERT_NONE, version=ssl.PROTOCOL_TLS_CLIENT) if use_ssl else None
    try:
        srv = ldap3.Server(s, get_info=get_info, connect_timeout=10, tls=tls_cfg)
        conn = ldap3.Connection(srv, user=bind_user, password=bind_pass,
                                auto_bind=True, authentication=ldap3.SIMPLE,
                                receive_timeout=10, auto_referrals=False)
    except ldap3.core.exceptions.LDAPBindError as e:
        # distinguish bad credentials from other bind failures
        raise ValueError("LDAP bind failed (invalid credentials or account locked): " + str(e))
    except ldap3.core.exceptions.LDAPSocketOpenError as e:
        raise ValueError("Cannot reach LDAP server (check IP/hostname/port/firewall): " + str(e))
    return conn

def ldap_search_func(q):
    """Shared LDAP search logic (used by /api/ldap/search and the employee LDAP import).
    Returns {"status": <http status>, "json": <payload dict>}."""
    row = _ldap_settings()
    if not (row.get("ldap_server") and row.get("ldap_base_dn") and row.get("ldap_bind_user") and row.get("ldap_bind_pass")):
        return {"status": 400, "json": {"ok": False, "error": "LDAP settings incomplete"}}
    try:
        import ldap3
        conn = _ldap_connect(row, get_info=ldap3.ALL)
        base_dn = row.get("ldap_base_dn").strip()
        # search by username OR name (Windows AD)
        sf = f"(&(|(objectClass=user)(objectClass=person))(|(sAMAccountName=*{q}*)(cn=*{q}*)(displayName=*{q}*)(mail=*{q}*)))"
        conn.search(base_dn, sf, attributes=["sAMAccountName","displayName","mail","department","title"])
        results = []
        for entry in conn.entries:
            results.append({
                "EmployeeID": str(entry.sAMAccountName) if "sAMAccountName" in entry else (str(entry.cn) if "cn" in entry else q),
                "EmployeeName": str(entry.displayName) if "displayName" in entry else (str(entry.cn) if "cn" in entry else q),
                "Email": str(entry.mail) if "mail" in entry else "",
                "Department": str(entry.department) if "department" in entry else "",
                "Designation": str(entry.title) if "title" in entry else "",
            })
        conn.unbind()
        return {"status": 200, "json": {"ok": True, "results": results}}
    except Exception as e:
        return {"status": 500, "json": {"ok": False, "error": str(e)}}

@app.route("/api/ldap/search")
@auth_required()
def ldap_search():
    q = (request.args.get("q") or "").strip()
    r = ldap_search_func(q)
    return jsonify(r["json"]), r["status"]

@app.route("/api/employees")
@auth_required(module="directory", level="read")
def list_employees():
    c = conn(); cur = c.cursor()
    cur.execute("SELECT * FROM Employees ORDER BY EmployeeName")
    rows = cur.fetchall(); c.close()
    return jsonify(rows)

@app.route("/api/employees", methods=["POST"])
@auth_required(module="directory", level="write")
def create_employee():
    import uuid
    data = request.get_json(force=True) or {}
    c = conn(); cur = c.cursor()
    emp = {
        "_id": uuid.uuid4().hex,
        "EmployeeID": data.get("EmployeeID") or "",
        "EmpCode": (data.get("EmpCode") or "").strip() or _next_emp_code(cur),
        "EmployeeName": data.get("EmployeeName") or "",
        "Designation": data.get("Designation") or "",
        "Department": data.get("Department") or "",
        "Email": data.get("Email") or "",
        "source": "manual"
    }
    cur.execute("""INSERT INTO Employees (_id, EmployeeID, EmpCode, EmployeeName, Designation, Department, Email, source)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (emp["_id"], emp["EmployeeID"], emp["EmpCode"], emp["EmployeeName"], emp["Designation"], emp["Department"], emp["Email"], emp["source"]))
    c.commit(); c.close()
    return jsonify(emp)

@app.route("/api/employees/<e_id>", methods=["PUT"])
@auth_required(module="directory", level="write")
def update_employee(e_id):
    data = request.get_json(force=True) or {}
    c = conn(); cur = c.cursor()
    cur.execute("SELECT _id FROM Employees WHERE _id=%s", [e_id])
    if not cur.fetchone():
        c.close(); return jsonify({"error": "not found"}), 404
    cur.execute("""UPDATE Employees SET EmployeeID=%s, EmpCode=%s, EmployeeName=%s, Designation=%s, Department=%s, Email=%s
                   WHERE _id=%s""",
                (data.get("EmployeeID") or "", data.get("EmpCode") or "", data.get("EmployeeName") or "", data.get("Designation") or "",
                 data.get("Department") or "", data.get("Email") or "", e_id))
    c.commit(); c.close()
    return jsonify({"ok": True})

@app.route("/api/employees/<e_id>", methods=["DELETE"])
@auth_required(module="directory", level="write")
def delete_employee(e_id):
    c = conn(); cur = c.cursor()
    cur.execute("SELECT EmployeeName FROM Employees WHERE _id=%s", [e_id])
    r = cur.fetchone()
    if not r:
        c.close(); return jsonify({"error": "not found"}), 404
    cur.execute("UPDATE Assets SET EmployeeID=NULL WHERE EmployeeID=(SELECT EmployeeID FROM Employees WHERE _id=%s)", [e_id])
    cur.execute("DELETE FROM Employees WHERE _id=%s", [e_id])
    c.commit(); c.close()
    audit(session.get("user"), "EMPLOYEE_DELETE", "", f"{r.get('EmployeeName','?')}")
    return jsonify({"ok": True})

@app.route("/api/employees/ldap-import", methods=["POST"])
@auth_required(module="directory", level="write")
def ldap_import_employees():
    data = request.get_json(force=True) or {}
    q = (data.get("q") or "").strip()
    if not q:
        return jsonify({"ok": False, "error": "Missing query"}), 400
    r = ldap_search_func(q)
    if r.get("status") != 200:
        return jsonify(r), r.get("status", 500)
    imported = []
    c = conn(); cur = c.cursor()
    for item in (r.get("json") or {}).get("results", []):
        import uuid
        emp_id = uuid.uuid4().hex
        cur.execute("""INSERT INTO Employees (_id, EmployeeID, EmpCode, EmployeeName, Designation, Department, Email, source)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,'ldap')""",
                    (emp_id, item.get("EmployeeID",""), _next_emp_code(cur), item.get("EmployeeName",""), item.get("Designation",""),
                     item.get("Department",""), item.get("Email","")))
        imported.append(item)
    c.commit(); c.close()
    return jsonify({"ok": True, "imported": len(imported), "employees": imported})

def ldap_sync_all(row):
    """Pull ALL user objects from AD (paged) and upsert into Employees. Returns summary dict."""
    import uuid
    c = conn(); cur = c.cursor()
    lc = _ldap_connect(row, get_info=ldap3.NONE)
    base_dn = row.get("ldap_base_dn").strip()
    # pull every user account, paged (AD caps unpaged results at 1000)
    sf = "(&(objectClass=user)(objectCategory=person))"
    attrs = ["sAMAccountName","displayName","givenName","sn","cn","mail","department","title","userPrincipalName"]
    entries = []
    entry_gen = lc.extend.standard.paged_search(base_dn, sf, attributes=attrs,
                                                paged_size=500, generator=True)
    seen = set()
    added = updated = 0
    for e in entry_gen:
        if e.get("type") != "searchResEntry":
            continue
        a = e.get("attributes", {}) or {}
        def _v(k):
            v = a.get(k)
            # unwrap ldap3 Attribute / list wrappers to a plain string
            try:
                if hasattr(v, "value"):
                    v = v.value
            except Exception:
                pass
            if isinstance(v, (list, tuple)):
                v = v[0] if v else ""
            if v is None:
                return ""
            return str(v).strip()
        sam = _v("sAMAccountName").lower()
        if not sam or sam in seen:
            continue
        seen.add(sam)
        name = _v("displayName") or _v("cn") or (_v("givenName") + " " + _v("sn")).strip() or sam
        email = _v("mail") or _v("userPrincipalName")
        dept = _v("department")
        desig = _v("title")
        cur.execute("SELECT _id FROM Employees WHERE EmployeeID=%s", (sam,))
        existing = cur.fetchone()
        if existing:
            cur.execute("UPDATE Employees SET EmployeeName=%s, Designation=%s, Department=%s, Email=%s, source='ldap' WHERE _id=%s",
                        (name, desig, dept, email, existing["_id"]))
            updated += 1
        else:
            cur.execute("""INSERT INTO Employees (_id, EmployeeID, EmpCode, EmployeeName, Designation, Department, Email, source)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,'ldap')""",
                        (uuid.uuid4().hex, sam, _next_emp_code(cur), name, desig, dept, email))
            added += 1
    try:
        lc.unbind()
    except Exception:
        pass
    c.commit(); c.close()
    return {"added": added, "updated": updated, "total": len(seen)}

@app.route("/api/employees/ldap-sync", methods=["POST"])
@auth_required(module="directory", level="write")
def ldap_sync_employees():
    row = _ldap_settings()
    if not (row.get("ldap_server") and row.get("ldap_base_dn") and row.get("ldap_bind_user") and row.get("ldap_bind_pass")):
        return jsonify({"ok": False, "error": "LDAP settings incomplete"}), 400
    try:
        res = ldap_sync_all(row)
        return jsonify({"ok": True, **res})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ---------- assets ----------
@app.route("/api/assets")
@auth_required(module="assets", level="read")
def list_assets():
    c = conn(); cur = c.cursor()
    q = request.args.get("q", "").strip(); sf = request.args.get("status", "").strip(); cf = request.args.get("col", "").strip()
    sql = "SELECT _id, " + ", ".join(f"`{col}`" for col in COLUMNS) + ", InvoiceFile FROM Assets WHERE is_deleted=0"
    where = []; params = []
    if sf: where.append("Status=%s"); params.append(sf)
    if q:
        if cf in COLUMNS:
            where.append(f"`{cf}` LIKE %s"); params.append(f"%{q}%")
        else:
            where.append("(" + " OR ".join(f"`{col}` LIKE %s" for col in COLUMNS) + ")")
            params += [f"%{q}%"] * len(COLUMNS)
    if where: sql += " AND " + " AND ".join(where)
    if request.args.get("order") == "recent":
        sql += " ORDER BY created_at IS NULL, created_at DESC, Name"
    else:
        sql += " ORDER BY AssetTag='', AssetTag, Name"
    cur.execute(sql, params); rows = cur.fetchall(); c.close()
    return jsonify([row_to_dict(r) for r in rows])

def _next_asset_tag(cur):
    cur.execute("SELECT MAX(CAST(SUBSTRING(AssetTag,4) AS UNSIGNED)) AS n FROM Assets WHERE AssetTag REGEXP '^IT-[0-9]+$'")
    n = (cur.fetchone() or {}).get("n") or 1000
    return f"IT-{n + 1}"

def _next_contract_tag(cur):
    cur.execute("SELECT MAX(CAST(SUBSTRING(contract_tag,4) AS UNSIGNED)) AS n FROM Contracts WHERE contract_tag REGEXP '^CT-[0-9]+$'")
    n = (cur.fetchone() or {}).get("n") or 0
    return f"CT-{n + 1:04d}"

def _next_emp_code(cur):
    cur.execute("SELECT MAX(CAST(SUBSTRING(EmpCode,5) AS UNSIGNED)) AS n FROM Employees WHERE EmpCode REGEXP '^EMP-[0-9]+$'")
    n = (cur.fetchone() or {}).get("n") or 0
    return f"EMP-{n + 1:03d}"

@app.route("/api/contracts/next-tag")
@auth_required(module="contracts", level="read")
def next_contract_tag():
    c = conn(); cur = c.cursor()
    tag = _next_contract_tag(cur)
    c.close()
    return jsonify({"tag": tag})

@app.route("/api/employees/next-code")
@auth_required(module="directory", level="read")
def next_emp_code():
    c = conn(); cur = c.cursor()
    code = _next_emp_code(cur)
    c.close()
    return jsonify({"code": code})

@app.route("/api/assets/next-tag")
@auth_required(module="assets", level="read")
def next_asset_tag():
    c = conn(); cur = c.cursor()
    tag = _next_asset_tag(cur)
    c.close()
    return jsonify({"tag": tag})

def _resolve_employee_name(cur, employee_id):
    """Employee Name -> display name, so Signed By reads a real name instead
    of the raw EmployeeID/username when an asset is auto-checked-out."""
    if not employee_id:
        return ""
    cur.execute("SELECT EmployeeName FROM Employees WHERE EmployeeID=%s", [employee_id])
    r = cur.fetchone()
    if r and r.get("EmployeeName"):
        return r["EmployeeName"]
    return employee_id

@app.route("/api/assets", methods=["POST"])
@auth_required(module="assets", level="write")
def create_asset():
    data = request.get_json(force=True)
    serial = (data.get("Serial") or "").strip()
    c = conn(); cur = c.cursor()
    if serial:
        cur.execute("SELECT _id, Name FROM Assets WHERE is_deleted=0 AND LOWER(Serial)=%s", [serial.lower()])
        dup = cur.fetchone()
        if dup:
            c.close()
            return jsonify({"error": f"Serial '{serial}' is already used by asset '{dup.get('Name') or dup['_id']}' -- no duplicate added"}), 409
    a_id = uuid.uuid4().hex
    if not (data.get("AssetTag") or "").strip():
        data["AssetTag"] = _next_asset_tag(cur)
    if data.get("Status") == "Checked-Out" and (data.get("EmployeeID") or "").strip():
        data["ReceivedBy"] = _resolve_employee_name(cur, data["EmployeeID"])
        data["NotesReceived"] = datetime.now().strftime("%Y-%m-%d")
    vals = [a_id] + [coerce_val(col, data.get(col)) for col in COLUMNS] + [datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
    cols = "_id, " + ", ".join(f"`{col}`" for col in COLUMNS) + ", created_at"
    ph = ", ".join(["%s"] * (len(COLUMNS) + 2))
    cur.execute(f"INSERT INTO Assets ({cols}) VALUES ({ph})", vals); c.commit(); c.close()
    send_notification("IT Guy: New asset added", f"Asset '{data.get('Name','?')}' (S/N {data.get('Serial','?')}) was added by {session.get('user')}.")
    if (data.get("EmployeeID") or "").strip():
        notify_person_asset_assigned(data["EmployeeID"], {**data, "_id": a_id}, checked_out=(data.get("Status") == "Checked-Out"))
    return jsonify({"ok": True, "_id": a_id})

@app.route("/api/assets/<a_id>", methods=["GET"])
@auth_required(module="assets", level="read")
def get_asset(a_id):
    c = conn(); cur = c.cursor()
    cur.execute("SELECT * FROM Assets WHERE _id=%s AND is_deleted=0", [a_id])
    row = cur.fetchone(); c.close()
    if not row: return jsonify({"error": "not found"}), 404
    return jsonify(row_to_dict(row))


@app.route("/api/assets/<a_id>", methods=["PUT"])
@auth_required(module="assets", level="write")
def update_asset(a_id):
    data = request.get_json(force=True)
    c = conn(); cur = c.cursor()
    # capture old values for history
    cur.execute("SELECT _id, " + ", ".join(f"`{col}`" for col in COLUMNS) + " FROM Assets WHERE _id=%s AND is_deleted=0", [a_id])
    old = cur.fetchone()
    if not old:
        c.close(); return jsonify({"error": "not found"}), 404
    old = row_to_dict(old)
    became_checked_out = data.get("Status") == "Checked-Out" and old.get("Status") != "Checked-Out"
    became_returned = old.get("Status") == "Checked-Out" and data.get("Status") not in (None, "", "Checked-Out")
    # Checking an asset out/in is just changing Status on this form now (no
    # separate checkout dialog) -- Signed By / Signed Date are derived here
    # instead of being asked for again, and the Checkouts history row is
    # opened/closed the same way the old dedicated checkout/checkin did.
    recv_by = None
    if became_checked_out:
        recv_by = _resolve_employee_name(cur, (data.get("EmployeeID") or old.get("EmployeeID") or "").strip())
        data["ReceivedBy"] = recv_by
        data["NotesReceived"] = datetime.now().strftime("%Y-%m-%d")
    elif became_returned:
        data["ReceivedBy"] = ""
        data["NotesReceived"] = ""
    sets = ", ".join(f"`{col}`=%s" for col in COLUMNS)
    vals = [coerce_val(col, data.get(col)) for col in COLUMNS] + [a_id]
    cur.execute(f"UPDATE Assets SET {sets} WHERE _id=%s", vals)
    if became_checked_out:
        cur.execute("INSERT INTO Checkouts (asset_id, username, checkout_date, expected_checkin, note) VALUES (%s,%s,%s,%s,%s)",
                    (a_id, recv_by or "", nowstr(), "", ""))
    elif became_returned:
        cur.execute("SELECT id FROM Checkouts WHERE asset_id=%s AND checkin_date IS NULL ORDER BY id DESC LIMIT 1", [a_id])
        co = cur.fetchone()
        if co:
            cur.execute("UPDATE Checkouts SET checkin_date=%s WHERE id=%s", (nowstr(), co["id"]))
    # history log (GLPI-style: every changed field recorded)
    hist = []
    for col in COLUMNS:
        nv = str(data.get(col) or "")
        ov = str(old.get(col) or "")
        if nv != ov:
            hist.append((a_id, session.get("user", "?"), col, ov, nv))
    if hist:
        cur.executemany("INSERT INTO History (asset_id, ts, user, field, old_val, new_val) VALUES (%s, NOW(), %s, %s, %s, %s)", hist)
    c.commit(); c.close()
    new_emp = (data.get("EmployeeID") or "").strip()
    emp_changed = new_emp and new_emp != (old.get("EmployeeID") or "").strip()
    if new_emp and (emp_changed or became_checked_out):
        notify_person_asset_assigned(new_emp, {**data, "_id": a_id}, checked_out=(data.get("Status") == "Checked-Out"))
    try:
        notify_asset_status_changed({**data, "_id": a_id}, old.get("Status"), data.get("Status"))
    except Exception as e:
        print("asset status-change notify error:", e)
    return jsonify({"ok": True})

@app.route("/api/assets/<a_id>", methods=["DELETE"])
@auth_required(module="assets", level="write")
def delete_asset(a_id):
    c = conn(); cur = c.cursor()
    cur.execute("SELECT Name, Serial FROM Assets WHERE _id=%s AND is_deleted=0", [a_id]); r = cur.fetchone()
    if not r:
        c.close(); return jsonify({"error": "not found"}), 404
    # GLPI-style soft delete: keep the row, just flag it
    cur.execute("UPDATE Assets SET is_deleted=1 WHERE _id=%s", [a_id])
    c.commit(); c.close()
    send_notification("IT Guy: Asset removed", f"Asset '{r.get('Name','?')}' (S/N {r.get('Serial','?')}) was removed by {session.get('user')}.")
    return jsonify({"ok": True})

@app.route("/api/assets/<a_id>/history")
@auth_required(module="assets", level="read")
def asset_history(a_id):
    c = conn(); cur = c.cursor()
    cur.execute("SELECT ts, user, field, old_val, new_val FROM History WHERE asset_id=%s ORDER BY ts DESC", [a_id])
    rows = cur.fetchall(); c.close()
    return jsonify([{"ts": str(r["ts"]), "user": r["user"], "field": r["field"],
                    "old_val": r["old_val"], "new_val": r["new_val"]} for r in rows])

@app.route("/api/assets/<a_id>/restore", methods=["POST"])
@auth_required(module="assets", level="write")
def restore_asset(a_id):
    c = conn(); cur = c.cursor()
    cur.execute("UPDATE Assets SET is_deleted=0 WHERE _id=%s", [a_id]); c.commit(); c.close()
    return jsonify({"ok": True})

@app.route("/api/assets/trash")
@auth_required(module="assets", level="read")
def trash_assets():
    c = conn(); cur = c.cursor()
    cur.execute("SELECT _id, " + ", ".join(f"`{col}`" for col in COLUMNS) + ", InvoiceFile FROM Assets WHERE is_deleted=1")
    rows = cur.fetchall(); c.close()
    return jsonify([row_to_dict(r) for r in rows])

def _purge_asset_row(cur, a_id, invoice_file):
    cur.execute("DELETE FROM Maintenance WHERE asset_id=%s", [a_id])
    cur.execute("DELETE FROM Checkouts WHERE asset_id=%s", [a_id])
    cur.execute("DELETE FROM History WHERE asset_id=%s", [a_id])
    cur.execute("DELETE FROM Assets WHERE _id=%s", [a_id])
    if invoice_file:
        try: os.remove(os.path.join(INVOICE_DIR, invoice_file))
        except Exception: pass

@app.route("/api/assets/<a_id>/permanent", methods=["DELETE"])
@auth_required(module="assets", level="write")
def permanent_delete_asset(a_id):
    c = conn(); cur = c.cursor()
    cur.execute("SELECT Name, Serial, InvoiceFile FROM Assets WHERE _id=%s AND is_deleted=1", [a_id])
    r = cur.fetchone()
    if not r:
        c.close(); return jsonify({"error": "not found in trash"}), 404
    _purge_asset_row(cur, a_id, r.get("InvoiceFile"))
    c.commit(); c.close()
    audit(session.get("user"), "PERMANENT_DELETE", a_id, f"{r.get('Name','?')} (S/N {r.get('Serial','?')})")
    return jsonify({"ok": True})

@app.route("/api/assets/trash/empty", methods=["POST"])
@auth_required(module="assets", level="write")
def empty_trash():
    c = conn(); cur = c.cursor()
    cur.execute("SELECT _id, Name, Serial, InvoiceFile FROM Assets WHERE is_deleted=1")
    rows = cur.fetchall()
    for r in rows:
        _purge_asset_row(cur, r["_id"], r.get("InvoiceFile"))
    c.commit(); c.close()
    audit(session.get("user"), "EMPTY_TRASH", "", f"{len(rows)} asset(s) permanently deleted")
    return jsonify({"ok": True, "deleted": len(rows)})

@app.route("/api/manufacturers", methods=["GET", "POST", "DELETE"])
@auth_required([ROLE_ADMIN, ROLE_EDIT])
def manufacturers_api():
    c = conn(); cur = c.cursor()
    if request.method == "GET":
        cur.execute("SELECT id, name FROM Manufacturers ORDER BY name"); rows = cur.fetchall(); c.close()
        return jsonify([{"id": r["id"], "name": r["name"]} for r in rows])
    if request.method == "POST":
        n = (request.get_json(force=True).get("name") or "").strip()
        if not n: return jsonify({"error": "name required"}), 400
        cur.execute("INSERT IGNORE INTO Manufacturers (name) VALUES (%s)", [n]); c.commit(); c.close()
        return jsonify({"ok": True})
    if request.method == "DELETE":
        mid = request.get_json(force=True).get("id")
        cur.execute("DELETE FROM Manufacturers WHERE id=%s", [mid]); c.commit(); c.close()
        return jsonify({"ok": True})

@app.route("/api/categories", methods=["GET", "POST", "DELETE"])
@auth_required([ROLE_ADMIN, ROLE_EDIT])
def categories_api():
    c = conn(); cur = c.cursor()
    if request.method == "GET":
        cur.execute("SELECT id, name FROM Categories ORDER BY name"); rows = cur.fetchall(); c.close()
        return jsonify([{"id": r["id"], "name": r["name"]} for r in rows])
    if request.method == "POST":
        n = (request.get_json(force=True).get("name") or "").strip()
        if not n: return jsonify({"error": "name required"}), 400
        cur.execute("INSERT IGNORE INTO Categories (name) VALUES (%s)", [n]); c.commit(); c.close()
        return jsonify({"ok": True})
    if request.method == "DELETE":
        cid = request.get_json(force=True).get("id")
        cur.execute("DELETE FROM Categories WHERE id=%s", [cid]); c.commit(); c.close()
        return jsonify({"ok": True})

@app.route("/api/contract-types", methods=["GET", "POST", "DELETE"])
@auth_required([ROLE_ADMIN, ROLE_EDIT])
def contract_types_api():
    c = conn(); cur = c.cursor()
    if request.method == "GET":
        cur.execute("SELECT id, name FROM ContractTypes ORDER BY name"); rows = cur.fetchall(); c.close()
        return jsonify([{"id": r["id"], "name": r["name"]} for r in rows])
    if request.method == "POST":
        n = (request.get_json(force=True).get("name") or "").strip()
        if not n: return jsonify({"error": "name required"}), 400
        cur.execute("INSERT IGNORE INTO ContractTypes (name) VALUES (%s)", [n]); c.commit(); c.close()
        return jsonify({"ok": True})
    if request.method == "DELETE":
        cid = request.get_json(force=True).get("id")
        cur.execute("DELETE FROM ContractTypes WHERE id=%s", [cid]); c.commit(); c.close()
        return jsonify({"ok": True})

@app.route("/api/departments", methods=["GET", "POST", "DELETE"])
@feature_required("directory.reflists")
def departments_api():
    c = conn(); cur = c.cursor()
    if request.method == "GET":
        cur.execute("SELECT id, name FROM Departments ORDER BY name"); rows = cur.fetchall(); c.close()
        return jsonify([{"id": r["id"], "name": r["name"]} for r in rows])
    if request.method == "POST":
        n = (request.get_json(force=True).get("name") or "").strip()
        if not n: return jsonify({"error": "name required"}), 400
        cur.execute("INSERT IGNORE INTO Departments (name) VALUES (%s)", [n]); c.commit(); c.close()
        return jsonify({"ok": True})
    if request.method == "DELETE":
        did = request.get_json(force=True).get("id")
        cur.execute("DELETE FROM Departments WHERE id=%s", [did]); c.commit(); c.close()
        return jsonify({"ok": True})

@app.route("/api/designations", methods=["GET", "POST", "DELETE"])
@feature_required("directory.reflists")
def designations_api():
    c = conn(); cur = c.cursor()
    if request.method == "GET":
        cur.execute("SELECT id, name FROM Designations ORDER BY name"); rows = cur.fetchall(); c.close()
        return jsonify([{"id": r["id"], "name": r["name"]} for r in rows])
    if request.method == "POST":
        n = (request.get_json(force=True).get("name") or "").strip()
        if not n: return jsonify({"error": "name required"}), 400
        cur.execute("INSERT IGNORE INTO Designations (name) VALUES (%s)", [n]); c.commit(); c.close()
        return jsonify({"ok": True})
    if request.method == "DELETE":
        did = request.get_json(force=True).get("id")
        cur.execute("DELETE FROM Designations WHERE id=%s", [did]); c.commit(); c.close()
        return jsonify({"ok": True})

@app.route("/api/models", methods=["GET", "POST", "DELETE"])
@auth_required([ROLE_ADMIN, ROLE_EDIT])
def models_api():
    c = conn(); cur = c.cursor()
    if request.method == "GET":
        cur.execute("""SELECT m.id, m.name, m.manufacturer_id, COALESCE(man.name,'') AS manufacturer
                       FROM Models m LEFT JOIN Manufacturers man ON m.manufacturer_id=man.id ORDER BY m.name""")
        rows = cur.fetchall(); c.close()
        return jsonify([{"id": r["id"], "name": r["name"], "manufacturer_id": r["manufacturer_id"], "manufacturer": r["manufacturer"]} for r in rows])
    if request.method == "POST":
        d = request.get_json(force=True)
        n = (d.get("name") or "").strip(); mid = d.get("manufacturer_id") or None
        if not n: return jsonify({"error": "name required"}), 400
        cur.execute("INSERT IGNORE INTO Models (name, manufacturer_id) VALUES (%s, %s)", [n, mid]); c.commit(); c.close()
        return jsonify({"ok": True})
    if request.method == "DELETE":
        mid = request.get_json(force=True).get("id")
        cur.execute("DELETE FROM Models WHERE id=%s", [mid]); c.commit(); c.close()
        return jsonify({"ok": True})

@app.route("/api/import", methods=["POST"])
@feature_required("assets.import")
def import_excel():
    if "file" not in request.files:
        return jsonify({"error": "no file"}), 400
    f = request.files["file"]
    wb = load_workbook(io.BytesIO(f.read()), data_only=True); ws = wb.active
    data = list(ws.iter_rows(values_only=True))
    if not data:
        return jsonify({"error": "empty"}), 400
    header = [str(h).strip() if h else "" for h in data[0]]
    c = conn(); cur = c.cursor(); added = updated = 0
    seen_types = set()
    for raw in data[1:]:
        if raw is None or all(v is None or str(v).strip() == "" for v in raw):
            continue
        rec = {header[i]: (raw[i] if i < len(raw) else None) for i in range(len(header))}
        row = {
            "Name": rec.get("Name") or rec.get("ASSET") or rec.get("Asset Name") or rec.get("Item") or "",
            "Type": rec.get("Type") or rec.get("Category") or rec.get("Asset Type") or "",
            "Serial": rec.get("Serial") or rec.get("Serial No") or rec.get("Serial Number") or "",
            "Location": rec.get("Location") or rec.get("Site") or rec.get("Place") or "",
            "Status": rec.get("Status") or "Active",
            "ReceivedBy": rec.get("ReceivedBy") or rec.get("Received By") or rec.get("Owner") or rec.get("User") or "",
            "Notes": rec.get("Notes") or rec.get("Remark") or rec.get("Comments") or "",
            "PurchaseDate": rec.get("PurchaseDate") or rec.get("Purchase Date") or rec.get("Bought") or "",
        }
        t = str(row.get("Type") or "").strip()
        if t and t not in seen_types:
            seen_types.add(t)
            cur.execute("INSERT IGNORE INTO Categories (name) VALUES (%s)", [t])
        serial = str(row["Serial"]).strip()
        if serial:
            cur.execute("SELECT _id FROM Assets WHERE Serial=%s", [serial]); ex = cur.fetchone()
            if ex:
                sets = ", ".join(f"`{col}`=%s" for col in COLUMNS)
                cur.execute(f"UPDATE Assets SET {sets} WHERE _id=%s", [coerce_val(col, row.get(col, "")) for col in COLUMNS] + [ex["_id"]])
                updated += 1; continue
        a_id = uuid.uuid4().hex
        vals = [a_id] + [coerce_val(col, row.get(col, "")) for col in COLUMNS]
        cols = "_id, " + ", ".join(f"`{col}`" for col in COLUMNS)
        ph = ", ".join(["%s"] * (len(COLUMNS) + 1))
        cur.execute(f"INSERT INTO Assets ({cols}) VALUES ({ph})", vals); added += 1
    c.commit(); c.close()
    return jsonify({"ok": True, "added": added, "updated": updated})

@app.route("/api/catalog/import", methods=["POST"])
@auth_required([ROLE_ADMIN, ROLE_EDIT])
def import_catalog():
    """Bulk-add Item Categories / Manufacturers / Models from an uploaded
    .xlsx/.xls/.csv sheet with Category / Manufacturer / Model columns (any
    subset -- a row can fill in just one of them, or a Manufacturer+Model
    pair). Existing entries are skipped, not duplicated."""
    if "file" not in request.files:
        return jsonify({"error": "no file"}), 400
    f = request.files["file"]
    fname = (f.filename or "").lower()
    raw = f.read()
    if fname.endswith(".csv"):
        import csv as _csv, io as _io
        text = raw.decode("utf-8-sig", errors="replace")
        rows = list(_csv.reader(_io.StringIO(text)))
    else:
        wb = load_workbook(io.BytesIO(raw), data_only=True); ws = wb.active
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
    if not rows:
        return jsonify({"error": "empty file"}), 400
    header = [str(h).strip() if h else "" for h in rows[0]]
    def hidx(*names):
        for n in names:
            for i, h in enumerate(header):
                if h.lower() == n.lower():
                    return i
        return -1
    ci, mi, di = hidx("Category", "Item Category", "Type"), hidx("Manufacturer", "Brand"), hidx("Model")
    if ci < 0 and mi < 0 and di < 0:
        return jsonify({"error": "no Category / Manufacturer / Model column found in the header row"}), 400
    def gv(row, idx):
        if idx < 0 or idx >= len(row) or row[idx] is None:
            return ""
        return str(row[idx]).strip()
    c = conn(); cur = c.cursor()
    added_cat = added_mfr = added_mod = 0
    mfr_id_cache = {}
    for row in rows[1:]:
        if row is None or all(v is None or str(v).strip() == "" for v in row):
            continue
        cat, mfr, mod = gv(row, ci), gv(row, mi), gv(row, di)
        if cat:
            cur.execute("INSERT IGNORE INTO Categories (name) VALUES (%s)", [cat])
            if cur.rowcount: added_cat += 1
        mfr_id = None
        if mfr:
            if mfr not in mfr_id_cache:
                cur.execute("INSERT IGNORE INTO Manufacturers (name) VALUES (%s)", [mfr])
                if cur.rowcount: added_mfr += 1
                cur.execute("SELECT id FROM Manufacturers WHERE name=%s", [mfr])
                mrow = cur.fetchone()
                mfr_id_cache[mfr] = mrow["id"] if mrow else None
            mfr_id = mfr_id_cache[mfr]
        if mod:
            cur.execute("INSERT IGNORE INTO Models (name, manufacturer_id) VALUES (%s, %s)", [mod, mfr_id])
            if cur.rowcount: added_mod += 1
    c.commit(); c.close()
    return jsonify({"ok": True, "categories": added_cat, "manufacturers": added_mfr, "models": added_mod})

@app.route("/api/directory/import", methods=["POST"])
@auth_required([ROLE_ADMIN, ROLE_EDIT])
def import_directory():
    """Bulk-add Departments / Locations / Designations from an uploaded
    .xlsx/.xls/.csv sheet (any subset of those columns). Existing entries
    are skipped, not duplicated."""
    if "file" not in request.files:
        return jsonify({"error": "no file"}), 400
    f = request.files["file"]
    fname = (f.filename or "").lower()
    raw = f.read()
    if fname.endswith(".csv"):
        import csv as _csv, io as _io
        text = raw.decode("utf-8-sig", errors="replace")
        rows = list(_csv.reader(_io.StringIO(text)))
    else:
        wb = load_workbook(io.BytesIO(raw), data_only=True); ws = wb.active
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
    if not rows:
        return jsonify({"error": "empty file"}), 400
    header = [str(h).strip() if h else "" for h in rows[0]]
    def hidx(*names):
        for n in names:
            for i, h in enumerate(header):
                if h.lower() == n.lower():
                    return i
        return -1
    depi, loci, desi = hidx("Department"), hidx("Location", "Site"), hidx("Designation", "Title", "Job Title")
    if depi < 0 and loci < 0 and desi < 0:
        return jsonify({"error": "no Department / Location / Designation column found in the header row"}), 400
    def gv(row, idx):
        if idx < 0 or idx >= len(row) or row[idx] is None:
            return ""
        return str(row[idx]).strip()
    c = conn(); cur = c.cursor()
    added_dep = added_loc = added_des = 0
    for row in rows[1:]:
        if row is None or all(v is None or str(v).strip() == "" for v in row):
            continue
        dep, loc, des = gv(row, depi), gv(row, loci), gv(row, desi)
        if dep:
            cur.execute("INSERT IGNORE INTO Departments (name) VALUES (%s)", [dep])
            if cur.rowcount: added_dep += 1
        if loc:
            cur.execute("INSERT IGNORE INTO Locations (name, parent_id) VALUES (%s, 0)", [loc])
            if cur.rowcount: added_loc += 1
        if des:
            cur.execute("INSERT IGNORE INTO Designations (name) VALUES (%s)", [des])
            if cur.rowcount: added_des += 1
    c.commit(); c.close()
    return jsonify({"ok": True, "departments": added_dep, "locations": added_loc, "designations": added_des})

@app.route("/api/export")
@feature_required("assets.export")
def export_excel():
    c = conn(); cur = c.cursor()
    cur.execute("SELECT _id, " + ", ".join(f"`{col}`" for col in COLUMNS) + ", InvoiceFile FROM Assets WHERE is_deleted=0 ORDER BY Name")
    rows = cur.fetchall(); c.close()
    wb = Workbook(); ws = wb.active; ws.title = "Assets"; ws.append(COLUMNS)
    for r in rows: ws.append([r.get(col, "") for col in COLUMNS])
    buf = io.BytesIO(); wb.save(buf); data = buf.getvalue()
    return Response(data,
                    mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": "attachment; filename=assets_export.xlsx"})

CONTRACT_EXPORT_COLS = ["name", "type", "vendor", "start_date", "end_date", "cost", "employee_id", "location", "department", "license_key", "note"]
CONTRACT_EXPORT_LABELS = {"name": "Name", "type": "Type", "vendor": "Vendor", "start_date": "Start Date",
                          "end_date": "End Date", "cost": "Cost", "employee_id": "Employee ID", "location": "Location",
                          "department": "Department", "license_key": "License Key", "note": "Note"}

@app.route("/api/contracts/export")
@auth_required(module="contracts", level="read")
def export_contracts_excel():
    c = conn(); cur = c.cursor()
    cur.execute("SELECT * FROM Contracts WHERE is_deleted=0 ORDER BY id")
    rows = cur.fetchall(); c.close()
    wb = Workbook(); ws = wb.active; ws.title = "Contracts"
    ws.append([CONTRACT_EXPORT_LABELS[c_] for c_ in CONTRACT_EXPORT_COLS])
    for r in rows: ws.append([r.get(c_, "") for c_ in CONTRACT_EXPORT_COLS])
    buf = io.BytesIO(); wb.save(buf); data = buf.getvalue()
    return Response(data,
                    mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": "attachment; filename=contracts_export.xlsx"})

@app.route("/api/contracts/import", methods=["POST"])
@auth_required(module="contracts", level="write")
def import_contracts_excel():
    if "file" not in request.files:
        return jsonify({"error": "no file"}), 400
    f = request.files["file"]
    wb = load_workbook(io.BytesIO(f.read()), data_only=True); ws = wb.active
    data = list(ws.iter_rows(values_only=True))
    if not data:
        return jsonify({"error": "empty"}), 400
    header = [str(h).strip() if h else "" for h in data[0]]
    def hidx(*names):
        for n in names:
            for i, h in enumerate(header):
                if h.lower() == n.lower():
                    return i
        return -1
    idx = {
        "name": hidx("Name", "Contract Name"), "type": hidx("Type", "Contract Type"),
        "vendor": hidx("Vendor", "Company", "Vendor / Company"), "start_date": hidx("Start Date", "Start"),
        "end_date": hidx("End Date", "End", "End / Renewal Date"), "cost": hidx("Cost", "Price", "Amount"),
        "employee_id": hidx("Employee ID", "Employee"), "location": hidx("Location"),
        "department": hidx("Department"), "license_key": hidx("License Key"), "note": hidx("Note", "Notes"),
    }
    def gv(row, key):
        i = idx[key]
        if i < 0 or i >= len(row) or row[i] is None:
            return ""
        return str(row[i]).strip()
    c = conn(); cur = c.cursor(); added = 0; seen_types = set()
    for raw in data[1:]:
        if raw is None or all(v is None or str(v).strip() == "" for v in raw):
            continue
        name = gv(raw, "name")
        if not name:
            continue
        t = gv(raw, "type")
        if t and t not in seen_types:
            seen_types.add(t)
            cur.execute("INSERT IGNORE INTO ContractTypes (name) VALUES (%s)", [t])
        cost_raw = gv(raw, "cost")
        try: cost = float(cost_raw) if cost_raw else 0
        except Exception: cost = 0
        cur.execute("""INSERT INTO Contracts (name, vendor, type, start_date, end_date, cost, employee_id, location, department, license_key, note)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (name, gv(raw, "vendor"), t, gv(raw, "start_date"), gv(raw, "end_date"), cost,
                     gv(raw, "employee_id"), gv(raw, "location"), gv(raw, "department"), gv(raw, "license_key"), gv(raw, "note")))
        added += 1
    c.commit(); c.close()
    return jsonify({"ok": True, "added": added})

def _valid_role(name):
    """A role is valid if it's one of the 3 built-ins or a custom role someone
    created on the Roles page."""
    if name in ROLES:
        return True
    try:
        c = conn(); cur = c.cursor()
        cur.execute("SELECT id FROM Roles WHERE name=%s", [name]); r = cur.fetchone(); c.close()
        return bool(r)
    except Exception:
        return False

# ---------- users (admin only) ----------
@app.route("/api/users")
@auth_required([ROLE_ADMIN])
def list_users():
    c = conn(); cur = c.cursor()
    cur.execute("SELECT username, role, display, email, totp_enabled, email_otp_enabled FROM Users ORDER BY role, username"); rows = cur.fetchall(); c.close()
    return jsonify([{"username": r["username"], "role": r["role"], "display": r["display"], "email": r.get("email", ""),
                     "totp_enabled": bool(r.get("totp_enabled")), "email_otp_enabled": bool(r.get("email_otp_enabled"))} for r in rows])

@app.route("/api/users", methods=["POST"])
@auth_required([ROLE_ADMIN])
def create_user():
    d = request.get_json(force=True)
    u = (d.get("username") or "").strip(); pw = d.get("password", ""); role = d.get("role", ROLE_VIEW); disp = d.get("display", "") or u; em = d.get("email", "").strip()
    if not u or not pw: return jsonify({"error": "username and password required"}), 400
    if not _valid_role(role): return jsonify({"error": "invalid role"}), 400
    c = conn(); cur = c.cursor()
    cur.execute("SELECT username FROM Users WHERE username=%s", [u])
    if cur.fetchone(): c.close(); return jsonify({"error": "user exists"}), 409
    cur.execute("INSERT INTO Users (username, password, role, display, email) VALUES (%s,%s,%s,%s,%s)",
                (u, hash_pw(pw), role, disp, em)); c.commit(); c.close()
    return jsonify({"ok": True})

@app.route("/api/users/<u>", methods=["PUT"])
@auth_required([ROLE_ADMIN])
def update_user(u):
    d = request.get_json(force=True)
    c = conn(); cur = c.cursor()
    cur.execute("SELECT username, role FROM Users WHERE username=%s", [u]); existing = cur.fetchone()
    if not existing: c.close(); return jsonify({"error": "not found"}), 404
    if existing["role"] == ROLE_ADMIN and d.get("role") != ROLE_ADMIN:
        cur.execute("SELECT COUNT(*) AS n FROM Users WHERE role=%s", [ROLE_ADMIN]); cnt = cur.fetchone()["n"]
        if cnt <= 1: c.close(); return jsonify({"error": "cannot demote last admin"}), 403
    sets = []; vals = []
    if "role" in d and _valid_role(d["role"]): sets.append("role=%s"); vals.append(d["role"])
    if "display" in d: sets.append("display=%s"); vals.append(d["display"])
    if "email" in d: sets.append("email=%s"); vals.append(d["email"].strip())
    if d.get("password"): sets.append("password=%s"); vals.append(hash_pw(d["password"]))
    if sets:
        cur.execute("UPDATE Users SET " + ", ".join(sets) + " WHERE username=%s", vals + [u]); c.commit()
    c.close(); return jsonify({"ok": True})

@app.route("/api/users/<u>", methods=["DELETE"])
@auth_required([ROLE_ADMIN])
def delete_user(u):
    if u == session.get("user"): return jsonify({"error": "cannot delete yourself"}), 403
    c = conn(); cur = c.cursor()
    cur.execute("SELECT role FROM Users WHERE username=%s", [u]); existing = cur.fetchone()
    if not existing: c.close(); return jsonify({"error": "not found"}), 404
    if existing["role"] == ROLE_ADMIN:
        cur.execute("SELECT COUNT(*) AS n FROM Users WHERE role=%s", [ROLE_ADMIN]); cnt = cur.fetchone()["n"]
        if cnt <= 1: c.close(); return jsonify({"error": "cannot delete last admin"}), 403
    cur.execute("DELETE FROM Users WHERE username=%s", [u]); c.commit(); c.close()
    return jsonify({"ok": True})

PERM_LEVELS = ("none", "read", "write")

@app.route("/api/features")
@auth_required([ROLE_ADMIN])
def list_features():
    """The permission catalogue the role editor renders."""
    return jsonify([{"key": g["key"], "label": g["label"], "module": g["module"],
                     "items": [{"key": k, "label": lbl, "level": lvl}
                               for (k, lbl, lvl) in g["items"]]}
                    for g in FEATURE_GROUPS])


@app.route("/api/roles")
@auth_required([ROLE_ADMIN])
def list_roles():
    c = conn(); cur = c.cursor()
    cur.execute("SELECT id, name, perm_assets, perm_contracts, perm_directory, perm_tickets, "
                "perm_settings, perms_json FROM Roles ORDER BY name")
    rows = cur.fetchall(); c.close()
    out = []
    for r in rows:
        d = {k: v for k, v in dict(r).items() if k != "perms_json"}
        # resolved rather than raw, so a legacy role reports the leaves it
        # actually has rather than an empty list
        d["features"] = sorted(_role_features(r["name"]))
        out.append(d)
    return jsonify(out)


def _role_body(d):
    """Read a role off the wire.

    Feature leaves are authoritative when present, and the module columns are
    derived from them -- one source of truth, so the coarse levels every
    existing route check reads can never drift from what the admin ticked.
    Callers that still send only perm_* (the Android app, scripts) keep
    working: their module levels are expanded into the matching leaves.
    """
    name = (d.get("name") or "").strip()[:50]
    if isinstance(d.get("features"), list):
        granted = {k for k in d["features"] if k in FEATURE_LEVEL}
        perms = _modules_from_features(granted)
    else:
        perms = {}
        for k in ("assets", "contracts", "directory", "tickets", "settings"):
            v = (d.get(f"perm_{k}") or "none").lower()
            perms[k] = v if v in PERM_LEVELS else "none"
        granted = _features_from_modules(perms)
    return name, perms, sorted(granted)


@app.route("/api/roles", methods=["POST"])
@auth_required([ROLE_ADMIN])
def create_role():
    d = request.get_json(force=True) or {}
    name, perms, granted = _role_body(d)
    if not name: return jsonify({"error": "name required"}), 400
    if name in ROLES: return jsonify({"error": "that name is a built-in role"}), 409
    c = conn(); cur = c.cursor()
    cur.execute("SELECT id FROM Roles WHERE name=%s", [name])
    if cur.fetchone(): c.close(); return jsonify({"error": "a role with that name already exists"}), 409
    cur.execute("INSERT INTO Roles (name, perm_assets, perm_contracts, perm_directory, perm_tickets, perm_settings, perms_json) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (name, perms["assets"], perms["contracts"], perms["directory"],
                 perms["tickets"], perms["settings"], json.dumps(granted)))
    c.commit(); c.close()
    audit(session.get("user"), "ROLE", name, f"created with {len(granted)} permission(s)")
    return jsonify({"ok": True, "features": granted})


@app.route("/api/roles/<int:rid>", methods=["PUT"])
@auth_required([ROLE_ADMIN])
def update_role(rid):
    d = request.get_json(force=True) or {}
    c = conn(); cur = c.cursor()
    cur.execute("SELECT name FROM Roles WHERE id=%s", [rid]); existing = cur.fetchone()
    if not existing: c.close(); return jsonify({"error": "not found"}), 404
    _, perms, granted = _role_body(d)
    cur.execute("UPDATE Roles SET perm_assets=%s, perm_contracts=%s, perm_directory=%s, "
                "perm_tickets=%s, perm_settings=%s, perms_json=%s WHERE id=%s",
                (perms["assets"], perms["contracts"], perms["directory"],
                 perms["tickets"], perms["settings"], json.dumps(granted), rid))
    c.commit(); c.close()
    audit(session.get("user"), "ROLE", existing["name"], f"updated to {len(granted)} permission(s)")
    return jsonify({"ok": True, "features": granted})

@app.route("/api/roles/<int:rid>", methods=["DELETE"])
@auth_required([ROLE_ADMIN])
def delete_role(rid):
    c = conn(); cur = c.cursor()
    cur.execute("SELECT name FROM Roles WHERE id=%s", [rid]); existing = cur.fetchone()
    if not existing: c.close(); return jsonify({"error": "not found"}), 404
    cur.execute("SELECT COUNT(*) AS n FROM Users WHERE role=%s", [existing["name"]])
    n = cur.fetchone()["n"]
    if n: c.close(); return jsonify({"error": f"{n} user(s) still have this role -- reassign them first"}), 409
    cur.execute("DELETE FROM Roles WHERE id=%s", [rid]); c.commit(); c.close()
    return jsonify({"ok": True})

@app.route("/api/profile/password", methods=["POST"])
@auth_required()
def change_own_password():
    d = request.get_json(force=True)
    old = d.get("old", ""); new = d.get("new", "")
    if not new: return jsonify({"error": "new password required"}), 400
    c = conn(); cur = c.cursor()
    cur.execute("SELECT password FROM Users WHERE username=%s", [session["user"]]); row = cur.fetchone()
    if not row or not verify_pw(old, row["password"]): c.close(); return jsonify({"error": "old password incorrect"}), 403
    cur.execute("UPDATE Users SET password=%s WHERE username=%s", (hash_pw(new), session["user"])); c.commit(); c.close()
    return jsonify({"ok": True})

# ---------- two-factor auth (self-service: TOTP authenticator app + email OTP) ----------
@app.route("/api/2fa/status")
@auth_required()
def twofa_status():
    c = conn(); cur = c.cursor()
    cur.execute("SELECT email, totp_enabled, email_otp_enabled FROM Users WHERE username=%s", [session["user"]])
    row = cur.fetchone() or {}
    cur.execute("SELECT smtp_host FROM Settings WHERE id=1"); s = cur.fetchone() or {}
    c.close()
    return jsonify({"totp_enabled": bool(row.get("totp_enabled")), "email_otp_enabled": bool(row.get("email_otp_enabled")),
                    "email": row.get("email") or "", "smtp_configured": bool(s.get("smtp_host"))})

@app.route("/api/2fa/totp/setup", methods=["POST"])
@auth_required()
def twofa_totp_setup():
    secret = pyotp.random_base32()
    session["totp_pending_secret"] = secret
    c = conn(); cur = c.cursor()
    cur.execute("SELECT app_name FROM Settings WHERE id=1"); s = cur.fetchone() or {}
    c.close()
    issuer = s.get("app_name") or "IT-Vault"
    otpauth_url = pyotp.TOTP(secret).provisioning_uri(name=session["user"], issuer_name=issuer)
    img = qrcode.make(otpauth_url, image_factory=qrcode.image.svg.SvgPathImage, box_size=8)
    buf = io.BytesIO(); img.save(buf)
    qr_svg = buf.getvalue().decode("utf-8")
    qr_svg = re.sub(r"<path ", '<path fill="#000" ', qr_svg, count=1)
    return jsonify({"secret": secret, "otpauth_url": otpauth_url, "qr_svg": qr_svg})

@app.route("/api/2fa/totp/confirm", methods=["POST"])
@auth_required()
def twofa_totp_confirm():
    secret = session.get("totp_pending_secret")
    if not secret: return jsonify({"error": "start setup first"}), 400
    d = request.get_json(force=True, silent=True) or {}
    code = (d.get("code") or "").strip()
    if not pyotp.TOTP(secret).verify(code, valid_window=1):
        return jsonify({"error": "Invalid code -- check your authenticator app and try again"}), 400
    c = conn(); cur = c.cursor()
    cur.execute("UPDATE Users SET totp_secret=%s, totp_enabled=1 WHERE username=%s", (secret, session["user"]))
    c.commit(); c.close()
    session.pop("totp_pending_secret", None)
    return jsonify({"ok": True})

@app.route("/api/2fa/totp/disable", methods=["POST"])
@auth_required()
def twofa_totp_disable():
    c = conn(); cur = c.cursor()
    cur.execute("UPDATE Users SET totp_secret='', totp_enabled=0 WHERE username=%s", [session["user"]])
    c.commit(); c.close()
    return jsonify({"ok": True})

@app.route("/api/2fa/email-otp/enable", methods=["POST"])
@auth_required()
def twofa_email_otp_enable():
    c = conn(); cur = c.cursor()
    cur.execute("SELECT email FROM Users WHERE username=%s", [session["user"]]); row = cur.fetchone() or {}
    cur.execute("SELECT smtp_host FROM Settings WHERE id=1"); s = cur.fetchone() or {}
    c.close()
    email = row.get("email") or ""
    if not email: return jsonify({"error": "Set an email on your profile first"}), 400
    if not s.get("smtp_host"): return jsonify({"error": "SMTP is not configured -- ask an admin to set it up in Settings"}), 400
    code = f"{secrets.randbelow(1000000):06d}"
    session["email_otp_pending_code"] = code
    session["email_otp_pending_sent_at"] = time.time()
    ok = _send_simple_email(email, "Confirm email sign-in codes", f"Your verification code is: {code}\n\nEnter this code to confirm email sign-in codes for your account.")
    if not ok: return jsonify({"error": "Could not send email -- check SMTP settings"}), 400
    return jsonify({"ok": True, "sent_to": email})

@app.route("/api/2fa/email-otp/confirm", methods=["POST"])
@auth_required()
def twofa_email_otp_confirm():
    pending = session.get("email_otp_pending_code")
    if not pending: return jsonify({"error": "start enabling email codes first"}), 400
    d = request.get_json(force=True, silent=True) or {}
    code = (d.get("code") or "").strip()
    if code != pending:
        return jsonify({"error": "Invalid code"}), 400
    c = conn(); cur = c.cursor()
    cur.execute("UPDATE Users SET email_otp_enabled=1 WHERE username=%s", [session["user"]])
    c.commit(); c.close()
    session.pop("email_otp_pending_code", None); session.pop("email_otp_pending_sent_at", None)
    return jsonify({"ok": True})

@app.route("/api/2fa/email-otp/disable", methods=["POST"])
@auth_required()
def twofa_email_otp_disable():
    c = conn(); cur = c.cursor()
    cur.execute("UPDATE Users SET email_otp_enabled=0 WHERE username=%s", [session["user"]])
    c.commit(); c.close()
    return jsonify({"ok": True})

@app.route("/api/users/<u>/2fa/disable", methods=["POST"])
@auth_required([ROLE_ADMIN])
def admin_disable_2fa(u):
    """Recovery valve for a locked-out user: an admin can force-disable both
    2FA methods without needing the user's authenticator or email access."""
    c = conn(); cur = c.cursor()
    cur.execute("UPDATE Users SET totp_secret='', totp_enabled=0, email_otp_enabled=0 WHERE username=%s", [u])
    c.commit(); c.close()
    return jsonify({"ok": True})

def _send_simple_email(to_email, subject, body, html_body=None):
    import smtplib
    from email.message import EmailMessage
    c = conn(); cur = c.cursor()
    cur.execute("SELECT smtp_host, smtp_port, smtp_user, smtp_pass, smtp_from, app_name FROM Settings WHERE id=1")
    s = cur.fetchone() or {}; c.close()
    if not s.get("smtp_host") or not to_email:
        return False
    try:
        bn = s.get("app_name") or "IT-Vault"
        msg = EmailMessage(); msg["Subject"] = f"{bn}: {subject}"
        msg["From"] = s.get("smtp_from") or s.get("smtp_user")
        msg["To"] = to_email; msg.set_content(body + _email_footer(bn))
        if html_body:
            # a plain-text link (what mail clients were rendering before)
            # still auto-links, but reads like any other line of text -- an
            # HTML alternative with a real styled button is what makes it
            # look like an action to take, not just a URL to notice.
            msg.add_alternative(html_body, subtype="html")
        with smtplib.SMTP(s["smtp_host"], int(s.get("smtp_port", 587) or 587), timeout=10) as sv:
            if s.get("smtp_user"): sv.starttls(); sv.login(s["smtp_user"], s.get("smtp_pass", ""))
            sv.send_message(msg)
        return True
    except Exception as e:
        print("email send error:", e); return False

def _button_email_html(heading, button_label, button_url):
    """Self-contained, inline-styled HTML for a transactional email: one
    line of context and a call-to-action button, nothing else -- no card,
    no branded header, no details table. No external stylesheet or CSS
    variables -- most mail clients (Outlook especially) strip <style>
    blocks and don't support var(), so every color here is a literal hex
    matching the app's red accent."""
    return f"""<!doctype html><html><body style="margin:0;padding:28px 16px;font-family:Arial,Helvetica,sans-serif;">
  <div style="max-width:480px;margin:0 auto;text-align:center;">
    <p style="font-size:15px;color:#111111;margin:0 0 20px;">{heading}</p>
    <a href="{button_url}" style="display:inline-block;padding:13px 32px;background:#ff3b30;
       color:#ffffff;text-decoration:none;font-weight:700;font-size:14px;border-radius:8px;
       letter-spacing:.3px;">{button_label}</a>
  </div>
</body></html>"""

# ---------- profile (self) ----------
@app.route("/api/profile", methods=["GET", "PUT"])
@auth_required()
def profile():
    c = conn(); cur = c.cursor()
    if request.method == "PUT":
        d = request.get_json(force=True)
        if "display" in d and d["display"]:
            cur.execute("UPDATE Users SET display=%s WHERE username=%s", (d["display"], session["user"]))
        if "email" in d:
            cur.execute("UPDATE Users SET email=%s WHERE username=%s", (d["email"].strip(), session["user"]))
        if "avatar" in d:
            cur.execute("UPDATE Users SET avatar=%s WHERE username=%s", (d["avatar"], session["user"]))
        if d.get("theme") in ("dark", "light"):
            cur.execute("UPDATE Settings SET theme=%s WHERE id=1", [d["theme"]])
        if d.get("old") and d.get("new"):
            cur.execute("SELECT password FROM Users WHERE username=%s", [session["user"]]); row = cur.fetchone()
            if not row or not verify_pw(d["old"], row["password"]): c.close(); return jsonify({"error": "old password incorrect"}), 403
            cur.execute("UPDATE Users SET password=%s WHERE username=%s", (hash_pw(d["new"]), session["user"]))
        c.commit(); c.close()
        return jsonify({"ok": True})
    cur.execute("SELECT username, display, email, role, avatar, api_key, last_login FROM Users WHERE username=%s", [session["user"]]); u = cur.fetchone() or {}
    c.close()
    return jsonify({"user": u.get("username"), "display": u.get("display", ""), "email": u.get("email", ""), "role": u.get("role", ""),
                    "avatar": u.get("avatar", ""), "api_key": u.get("api_key", ""), "last_login": u.get("last_login", "")})

@app.route("/api/profile/avatar", methods=["POST"])
@auth_required()
def profile_avatar():
    f = request.files.get("avatar") if request.files else None
    if not f: return jsonify({"error": "no file"}), 400
    data = f.read()
    if len(data) > 400 * 1024:
        return jsonify({"error": "image too large (max 400KB)"}), 400
    b64 = "data:" + (f.mimetype or "image/png") + ";base64," + base64.b64encode(data).decode()
    c = conn(); cur = c.cursor()
    cur.execute("UPDATE Users SET avatar=%s WHERE username=%s", (b64, session["user"]))
    c.commit(); c.close()
    return jsonify({"ok": True, "avatar": b64})

@app.route("/api/profile/apikey", methods=["POST"])
@auth_required()
def profile_apikey():
    new_key = secrets.token_hex(24)
    c = conn(); cur = c.cursor()
    cur.execute("UPDATE Users SET api_key=%s WHERE username=%s", (new_key, session["user"]))
    c.commit(); c.close()
    return jsonify({"api_key": new_key})

# ---------- test DB / LDAP connections ----------
@app.route("/api/test-db", methods=["POST"])
@auth_required([ROLE_ADMIN])
def test_db():
    d = request.get_json(force=True) or {}
    h = d.get("db_host", DB_HOST); p = int(d.get("db_port", DB_PORT)); n = d.get("db_name", DB_NAME)
    u = d.get("db_user", DB_USER); pw = d.get("db_pass", DB_PASS)
    try:
        c = pymysql.connect(host=h, port=p, user=u, password=pw, database=n,
                             charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor, connect_timeout=8)
        c.close()
        return jsonify({"ok": True, "msg": f"Connected to {h}:{p}/{n}"})
    except Exception as e:
        return jsonify({"ok": False, "msg": _db_error_help(e, h)}), 400

@app.route("/api/test-ldap", methods=["POST"])
@auth_required(module="settings", level="write")
def test_ldap():
    d = request.get_json(force=True) or {}
    row = {"ldap_server": d.get("ldap_server", ""), "ldap_domain": d.get("ldap_domain", ""),
           "ldap_bind_user": d.get("ldap_bind_user", ""), "ldap_bind_pass": d.get("ldap_bind_pass", ""),
           "ldap_base_dn": d.get("ldap_base_dn", "")}
    if not (row["ldap_server"] and row["ldap_base_dn"] and row["ldap_bind_user"] and row["ldap_bind_pass"]):
        return jsonify({"ok": False, "msg": "Fill server, base DN, bind user & password"}), 400
    try:
        import ssl
        conn = _ldap_connect(row, get_info=ldap3.NONE)
        conn.unbind()
        return jsonify({"ok": True, "msg": "LDAP bind successful"})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 400

def _unifi_request(cfg):
    """Log into a UniFi Controller and fetch its device + active-client lists.
    cfg: dict with unifi_host/port/site/user/pass/is_os/verify_ssl. Returns
    (devices, clients) raw dicts as the controller returns them. Raises
    Exception with a human-readable message on any failure."""
    import requests, urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    host = (cfg.get("unifi_host") or "").strip()
    port = int(cfg.get("unifi_port") or 443)
    site = (cfg.get("unifi_site") or "default").strip() or "default"
    user = (cfg.get("unifi_user") or "").strip()
    pw = cfg.get("unifi_pass") or ""
    is_os = bool(cfg.get("unifi_is_os"))
    verify_ssl = bool(cfg.get("unifi_verify_ssl"))
    if not host or not user or not pw:
        raise Exception("Host, username and password are required")
    base = f"https://{host}:{port}"
    s = requests.Session()
    login_url = base + ("/api/auth/login" if is_os else "/api/login")
    try:
        r = s.post(login_url, json={"username": user, "password": pw}, verify=verify_ssl, timeout=8)
    except requests.exceptions.SSLError:
        raise Exception("SSL certificate not trusted -- enable 'Verify SSL' only if the controller has a valid cert, otherwise leave it off")
    except requests.exceptions.RequestException as e:
        raise Exception(f"Could not reach {host}:{port} -- {e}")
    if r.status_code in (400, 401):
        raise Exception("Login failed -- check username/password")
    r.raise_for_status()
    headers = {}
    csrf = r.headers.get("X-CSRF-Token") or r.headers.get("x-csrf-token")
    if csrf:
        headers["X-CSRF-Token"] = csrf
    prefix = "/proxy/network" if is_os else ""
    def get(path):
        rr = s.get(f"{base}{prefix}/api/s/{site}/{path}", headers=headers, verify=verify_ssl, timeout=10)
        rr.raise_for_status()
        return (rr.json() or {}).get("data", [])
    devices = get("stat/device")
    clients = get("stat/sta")
    try:
        s.post(base + ("/api/auth/logout" if is_os else "/api/logout"), headers=headers, verify=verify_ssl, timeout=5)
    except Exception:
        pass
    return devices, clients

@app.route("/api/test-unifi", methods=["POST"])
@auth_required(module="settings", level="write")
def test_unifi():
    d = request.get_json(force=True) or {}
    c = conn(); cur = c.cursor()
    cur.execute("SELECT unifi_host, unifi_port, unifi_site, unifi_user, unifi_pass, unifi_is_os, unifi_verify_ssl FROM Settings WHERE id=1")
    saved = cur.fetchone() or {}; c.close()
    cfg = {
        "unifi_host": d.get("unifi_host") or saved.get("unifi_host") or "",
        "unifi_port": d.get("unifi_port") or saved.get("unifi_port") or 443,
        "unifi_site": d.get("unifi_site") or saved.get("unifi_site") or "default",
        "unifi_user": d.get("unifi_user") or saved.get("unifi_user") or "",
        "unifi_pass": d.get("unifi_pass") or saved.get("unifi_pass") or "",
        "unifi_is_os": d.get("unifi_is_os") if "unifi_is_os" in d else bool(saved.get("unifi_is_os")),
        "unifi_verify_ssl": d.get("unifi_verify_ssl") if "unifi_verify_ssl" in d else bool(saved.get("unifi_verify_ssl")),
    }
    try:
        devices, clients = _unifi_request(cfg)
        return jsonify({"ok": True, "msg": f"Connected -- {len(devices)} device(s), {len(clients)} active client(s)"})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 400

def _unifi_refresh(force=False):
    now = time.time()
    if not force and (now - _unifi_cache["ts"]) < _UNIFI_CACHE_TTL:
        return
    c = conn(); cur = c.cursor()
    cur.execute("""SELECT unifi_enabled, unifi_host, unifi_port, unifi_site, unifi_user, unifi_pass,
                   unifi_is_os, unifi_verify_ssl FROM Settings WHERE id=1""")
    cfg = cur.fetchone() or {}; c.close()
    if not cfg.get("unifi_enabled"):
        _unifi_cache.update(ts=now, devices=[], clients=[], error="not_configured")
        return
    try:
        devices, clients = _unifi_request(cfg)
        _unifi_cache.update(ts=now, devices=devices, clients=clients, error=None)
    except Exception as e:
        _unifi_cache.update(ts=now, devices=[], clients=[], error=str(e))

_UNIFI_TYPE_LABELS = {"uap": "Access Point", "usw": "Switch", "ugw": "Gateway", "udm": "Gateway", "uxg": "Gateway"}

@app.route("/api/unifi/devices")
@auth_required()
def unifi_devices():
    _unifi_refresh(force=request.args.get("force") == "1")
    out = [{
        "name": d.get("name") or d.get("model") or d.get("mac", ""),
        "model": d.get("model", ""),
        "type": _UNIFI_TYPE_LABELS.get(d.get("type", ""), d.get("type", "") or "Device"),
        "ip": d.get("ip", ""),
        "mac": d.get("mac", ""),
        "online": d.get("state") == 1,
        "version": d.get("version", ""),
        "uptime": d.get("uptime", 0),
        "num_sta": d.get("num_sta", d.get("user-num_sta", 0)) or 0,
    } for d in _unifi_cache["devices"]]
    return jsonify({"devices": out, "error": _unifi_cache["error"]})

@app.route("/api/unifi/clients")
@auth_required()
def unifi_clients():
    _unifi_refresh(force=request.args.get("force") == "1")
    out = [{
        "hostname": cl.get("hostname") or cl.get("name") or cl.get("mac", ""),
        "ip": cl.get("ip", ""),
        "mac": cl.get("mac", ""),
        "is_wired": bool(cl.get("is_wired")),
        "essid": cl.get("essid", ""),
        "network": cl.get("network", ""),
        "uptime": cl.get("uptime", 0),
        "signal": cl.get("signal"),
    } for cl in _unifi_cache["clients"]]
    return jsonify({"clients": out, "error": _unifi_cache["error"]})

# ---------- settings (admin) ----------
def _save_letterhead(fileobj):
    """Normalize an uploaded letterhead (PDF or image) to a single PNG.

    A PDF's first page is rasterized (via PyMuPDF) so every print/PDF surface
    in the app can just <img src=/letterhead.png> or embed the same PNG, no
    matter what was uploaded.

    The conversion happens entirely in memory and the result goes to the
    database. It used to render straight onto DATA_DIR/letterhead.png, so on
    an install whose data volume the app can't write to, a perfectly good
    upload came back as "[Errno 13] Permission denied" -- a storage problem
    reported as a bad file.
    """
    fname = (fileobj.filename or "").lower()
    data = fileobj.read(24 * 1024 * 1024 + 1)
    if not data:
        return False, "empty file"
    if len(data) > 24 * 1024 * 1024:
        return False, "that file is over 24MB -- please use a smaller one"
    try:
        if fname.endswith(".pdf") or data[:4] == b"%PDF":
            import pymupdf
            doc = pymupdf.open(stream=data, filetype="pdf")
            if doc.page_count < 1:
                doc.close()
                return False, "PDF has no pages"
            page = doc.load_page(0)
            pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2))  # ~144dpi
            png = pix.tobytes("png")
            doc.close()
        elif _sniff_image(data)[0]:
            from PIL import Image as PILImage
            buf = io.BytesIO()
            PILImage.open(io.BytesIO(data)).convert("RGB").save(buf, format="PNG")
            png = buf.getvalue()
        else:
            return False, "that file isn't a PDF or an image (PNG, JPEG, GIF, WebP)"
    except Exception as e:
        return False, f"could not read that file: {e}"
    # Bounded before it goes anywhere near the database, so the size of what
    # someone uploaded can't decide whether the save succeeds.
    png = _fit_png(png)
    print(f"[itvault] branding: letterhead {fname!r} -> {len(png)}B PNG", flush=True)
    ok, err = _brand_store("letterhead", LETTERHEAD_PATH, png)
    if not ok:
        print(f"[itvault] branding: letterhead NOT saved: {err}", flush=True)
    return ok, err

@app.route("/letterhead.png")
def letterhead_file():
    sent = _brand_send("letterhead", LETTERHEAD_PATH, "letterhead.png")
    if sent is not None:
        return sent
    from flask import Response as _R
    return _R(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xcf\xc0\xf0\x1f\x00\x05\x05\x02\x00\x9d\xfd\xa4\x1e\x00\x00\x00\x00IEND\xaeB`\x82",
                    mimetype="image/png")

@app.route("/api/settings", methods=["GET", "PUT"])
@auth_required(module="settings", level="read")
def settings():
    if request.method != "GET" and not _module_write_allowed("settings"):
        return jsonify({"error": "No access"}), 403
    c = conn(); cur = c.cursor()
    if request.method == "PUT":
        # accept JSON or multipart FormData (branding uses FormData)
        if request.content_type and "multipart/form-data" in request.content_type:
            d = request.form.to_dict()
            logo = request.files.get("logo") if "logo" in request.files else None
            letterhead = request.files.get("letterhead") if "letterhead" in request.files else None
            # Logged because a branding upload that silently does nothing is
            # indistinguishable, from the outside, from one the server never
            # received. An empty files list here means the browser did not
            # send the file, and no server-side change would ever fix that.
            print(f"[itvault] branding PUT: form={sorted(d.keys())} "
                  f"files={sorted(request.files.keys())} "
                  f"logo={getattr(logo, 'filename', None)!r} "
                  f"letterhead={getattr(letterhead, 'filename', None)!r}", flush=True)
        else:
            d = request.get_json(force=True) or {}
            logo = None
            letterhead = None
        # load current row so partial saves (e.g. branding only) don't reset other fields
        cur.execute("SELECT theme, smtp_host, smtp_port, smtp_user, smtp_pass, smtp_from, notify_new, notify_delete, app_name, logo_text, matrix_on, ldap_server, ldap_domain, ldap_bind_user, ldap_bind_pass, ldap_base_dn, qr_size, qr_fields, label_size, label_logo, theme_preset, bg_type, bg, comp_bg, radius, font, accent, accent2, language, currency, region, portal_token, sla_low, sla_normal, sla_high, sla_urgent, sla_breach_notify, auto_assign_roundrobin, notify_on_create, notify_on_resolve, notify_on_reply, unifi_enabled, unifi_host, unifi_port, unifi_site, unifi_user, unifi_pass, unifi_is_os, unifi_verify_ssl FROM Settings WHERE id=1")
        cur0 = cur.fetchone() or {}
        def gv(k, fb):
            return d.get(k) if (k in d and d.get(k) not in (None, "")) else cur0.get(k, fb)
        cur.execute("""UPDATE Settings SET theme=%s, smtp_host=%s, smtp_port=%s, smtp_user=%s,
                      smtp_pass=%s, smtp_from=%s, notify_new=%s, notify_delete=%s,
                      app_name=%s, logo_text=%s, matrix_on=%s,
                      ldap_server=%s, ldap_domain=%s, ldap_bind_user=%s, ldap_bind_pass=%s, ldap_base_dn=%s,
                      qr_size=%s, qr_fields=%s, label_size=%s, label_logo=%s,
                      theme_preset=%s, bg_type=%s, bg=%s, comp_bg=%s, radius=%s, font=%s, accent=%s, accent2=%s,
                      language=%s, currency=%s, region=%s, portal_token=%s,
                      sla_low=%s, sla_normal=%s, sla_high=%s, sla_urgent=%s, sla_breach_notify=%s,
                      auto_assign_roundrobin=%s, notify_on_create=%s, notify_on_resolve=%s, notify_on_reply=%s
                      WHERE id=1""",
                    (gv("theme","dark"), gv("smtp_host",""), int(gv("smtp_port",587) or 587),
                     gv("smtp_user",""), gv("smtp_pass",""), gv("smtp_from",""),
                     bool(d.get("notify_new", cur0.get("notify_new", True))), bool(d.get("notify_delete", cur0.get("notify_delete", True))),
                     (d.get("app_name", cur0.get("app_name","IT-Vault") )[:60]), (d.get("logo_text", cur0.get("logo_text","IT-Vault"))[:40]),
                     bool(d.get("matrix_on", cur0.get("matrix_on", True))),
                     (gv("ldap_server","") or "").strip(), (gv("ldap_domain","") or "").strip(),
                     (gv("ldap_bind_user","") or "").strip(), d.get("ldap_bind_pass", cur0.get("ldap_bind_pass","")),
                     (gv("ldap_base_dn","") or "").strip(),
                     int(gv("qr_size",160) or 160), (gv("qr_fields","Name,AssetID,Type,Serial,Status,Location") or "Name,AssetID,Type,Serial,Status,Location")[:255],
                     (gv("label_size","50.8x50.8") or "50.8x50.8")[:20],
                     bool(d.get("label_logo", cur0.get("label_logo", True))),
                     (gv("theme_preset","deepdark") or "deepdark")[:20], (gv("bg_type","solid") or "solid")[:12],
                     (gv("bg","#0a0d13") or "#0a0d13")[:40], (gv("comp_bg","#121826") or "#121826")[:40],
                     int(gv("radius",12) or 12), (gv("font","Rajdhani") or "Rajdhani")[:40],
                     (gv("accent","#ff3b30") or "#ff3b30")[:20], (gv("accent2","#c0392b") or "#c0392b")[:20],
                     (gv("language","en") or "en")[:10], (gv("currency","AED") or "AED")[:6],
                     (gv("region","UAE") or "UAE")[:40], (d.get("portal_token", cur0.get("portal_token","")) or "")[:64],
                     int(gv("sla_low",72) or 72), int(gv("sla_normal",24) or 24),
                     int(gv("sla_high",8) or 8), int(gv("sla_urgent",4) or 4),
                     bool(d.get("sla_breach_notify", cur0.get("sla_breach_notify", True))),
                     bool(d.get("auto_assign_roundrobin", cur0.get("auto_assign_roundrobin", False))),
                     bool(d.get("notify_on_create", cur0.get("notify_on_create", True))),
                     bool(d.get("notify_on_resolve", cur0.get("notify_on_resolve", True))),
                     bool(d.get("notify_on_reply", cur0.get("notify_on_reply", True)))))
        if any(k in d for k in ("unifi_enabled","unifi_host","unifi_port","unifi_site","unifi_user","unifi_pass","unifi_is_os","unifi_verify_ssl")):
            cur.execute("""UPDATE Settings SET unifi_enabled=%s, unifi_host=%s, unifi_port=%s, unifi_site=%s,
                          unifi_user=%s, unifi_pass=%s, unifi_is_os=%s, unifi_verify_ssl=%s WHERE id=1""",
                        (bool(d.get("unifi_enabled", cur0.get("unifi_enabled", False))),
                         (d.get("unifi_host", cur0.get("unifi_host","")) or "").strip()[:200],
                         int(d.get("unifi_port") or cur0.get("unifi_port") or 443),
                         (d.get("unifi_site", cur0.get("unifi_site","default")) or "default").strip()[:80],
                         (d.get("unifi_user", cur0.get("unifi_user","")) or "").strip()[:120],
                         d.get("unifi_pass", cur0.get("unifi_pass","")) if d.get("unifi_pass") else cur0.get("unifi_pass",""),
                         bool(d.get("unifi_is_os", cur0.get("unifi_is_os", True))),
                         bool(d.get("unifi_verify_ssl", cur0.get("unifi_verify_ssl", False)))))
            _unifi_cache["ts"] = 0  # force a fresh fetch with the new config on next widget load
        if any(k in d for k in ("company_phone", "company_address")):
            cur.execute("SELECT company_phone, company_address FROM Settings WHERE id=1")
            br0 = cur.fetchone() or {}
            cur.execute("UPDATE Settings SET company_phone=%s, company_address=%s WHERE id=1",
                        ((d.get("company_phone", br0.get("company_phone", "")) or "")[:60],
                         (d.get("company_address", br0.get("company_address", "")) or "")[:255]))
        if any(k in d for k in ("backup_schedule", "backup_scope", "backup_retain")):
            cur.execute("SELECT backup_schedule, backup_scope, backup_retain FROM Settings WHERE id=1")
            bk0 = cur.fetchone() or {}
            sched = (d.get("backup_schedule", bk0.get("backup_schedule", "off")) or "off").lower()
            if sched not in ("off", "daily", "weekly"):
                sched = "off"
            bscope = (d.get("backup_scope", bk0.get("backup_scope", "all")) or "all").lower()
            if bscope not in ("all", "config", "assets"):
                bscope = "all"
            try:
                retain = max(1, int(d.get("backup_retain") or bk0.get("backup_retain") or 7))
            except (TypeError, ValueError):
                retain = 7
            cur.execute("UPDATE Settings SET backup_schedule=%s, backup_scope=%s, backup_retain=%s WHERE id=1",
                        (sched, bscope, retain))
        # persist DB connection config (points the app at a different MariaDB)
        if any(k in d for k in ("db_host", "db_port", "db_name", "db_user", "db_pass")):
            save_db_config(d.get("db_host", DB_HOST), d.get("db_port", DB_PORT),
                           d.get("db_name", DB_NAME), d.get("db_user", DB_USER),
                           d.get("db_pass", DB_PASS))
        if logo:
            # This used to be wrapped in "except Exception: pass", so a logo
            # that could not be saved still answered {"ok": true} and left the
            # admin re-uploading it forever with nothing to go on.
            data = logo.read()
            sniffed = _sniff_image(data)[0]
            print(f"[itvault] branding: logo {logo.filename!r} {len(data)}B sniffed={sniffed}", flush=True)
            if not sniffed:
                c.commit(); c.close()
                return jsonify({"error": f"{logo.filename or 'that file'} isn't a PNG, JPEG, GIF, "
                                         f"WebP or HEIC image -- convert it and try again"}), 400
            data = _fit_png(data, LOGO_MAX_EDGE, LOGO_MAX_BYTES)
            print(f"[itvault] branding: logo stored as {len(data)}B", flush=True)
            ok, err = _brand_store("logo", LOGO_PATH, data)
            if not ok:
                c.commit(); c.close()
                return jsonify({"error": err or "could not save the logo"}), 500
        elif str(d.get("remove_logo", "")).lower() in ("1", "true"):
            cur.execute("UPDATE Settings SET logo=NULL WHERE id=1")
            try:
                open(LOGO_PATH, "wb").close()
            except Exception:
                pass
        if letterhead:
            ok, err = _save_letterhead(letterhead)
            if ok:
                cur.execute("UPDATE Settings SET has_letterhead=1 WHERE id=1")
            else:
                c.commit(); c.close()
                return jsonify({"error": err or "could not process letterhead file"}), 400
        elif str(d.get("remove_letterhead", "")).lower() in ("1", "true"):
            cur.execute("UPDATE Settings SET has_letterhead=0, letterhead=NULL WHERE id=1")
            try:
                open(LETTERHEAD_PATH, "wb").close()
            except Exception:
                pass
        c.commit(); c.close()
        return jsonify({"ok": True})
    cur.execute("SELECT * FROM Settings WHERE id=1"); s = cur.fetchone(); c.close()
    s = s or {}
    # secrets (LDAP bind pw, UniFi pw, DB pw) never round-trip to the browser --
    # the frontend only ever writes a NEW value for these, never reads the old
    # one back, so we just tell it whether one's already on file.
    return jsonify({k: s.get(k) for k in ["theme","smtp_host","smtp_port","smtp_user","smtp_from",
                                          "notify_new","notify_delete","app_name","logo_text","matrix_on",
                                          "ldap_server","ldap_domain","ldap_bind_user","ldap_base_dn",
                                          "qr_size","qr_fields","label_size","label_logo",
                                          "theme_preset","bg_type","bg","comp_bg","radius","font","accent","accent2",
                                          "language","currency","region","portal_token",
                                          "sla_low","sla_normal","sla_high","sla_urgent","sla_breach_notify",
                                          "auto_assign_roundrobin","notify_on_create","notify_on_resolve","notify_on_reply",
                                          "unifi_enabled","unifi_host","unifi_port","unifi_site","unifi_user",
                                          "unifi_is_os","unifi_verify_ssl",
                                          "backup_schedule","backup_scope","backup_retain","backup_last_run",
                                          "company_phone","company_address","has_letterhead"]} | {
                "db_host": DB_HOST, "db_port": DB_PORT, "db_name": DB_NAME, "db_user": DB_USER,
                "ldap_bind_pass_set": bool(s.get("ldap_bind_pass")),
                "unifi_pass_set": bool(s.get("unifi_pass")),
                "db_pass_set": bool(DB_PASS)})

# ---------- contracts / locations (GLPI-style) ----------
@app.route("/api/contracts", methods=["GET","POST","PUT","DELETE"])
@auth_required(module="contracts", level="read")
def contracts_api():
    if request.method != "GET" and not _module_write_allowed("contracts"):
        return jsonify({"error": "No access"}), 403
    c = conn(); cur = c.cursor()
    if request.method == "GET":
        cur.execute("SELECT * FROM Contracts WHERE is_deleted=0 ORDER BY id"); rows = cur.fetchall(); c.close()
        return jsonify([dict(r) for r in rows])
    if request.method == "POST":
        d = request.get_json(force=True)
        tag = (d.get("contract_tag") or "").strip() or _next_contract_tag(cur)
        cur.execute("""INSERT INTO Contracts (name, vendor, vendor_email, type, start_date, end_date, cost, billing_period, contract_tag, asset_id, employee_id, location, department, license_key, note)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (d.get("name",""), d.get("vendor",""), d.get("vendor_email","").strip() if d.get("vendor_email") else "",
                     d.get("type",""), d.get("start_date",""), d.get("end_date",""),
                     float(d.get("cost") or 0), d.get("billing_period") or "One-Time", tag, d.get("asset_id") or None, d.get("employee_id") or "",
                     d.get("location") or "", d.get("department") or "", d.get("license_key") or "", d.get("note","")))
        c.commit(); c.close()
        if (d.get("employee_id") or "").strip():
            notify_person_contract_assigned(d["employee_id"], d)
        return jsonify({"ok": True})
    if request.method == "PUT":
        d = request.get_json(force=True); cid = d.get("id")
        cur.execute("SELECT employee_id FROM Contracts WHERE id=%s", [cid]); old = cur.fetchone() or {}
        tag = (d.get("contract_tag") or "").strip() or _next_contract_tag(cur)
        cur.execute("""UPDATE Contracts SET name=%s, vendor=%s, vendor_email=%s, type=%s, start_date=%s, end_date=%s, cost=%s, billing_period=%s, contract_tag=%s, asset_id=%s,
                       employee_id=%s, location=%s, department=%s, license_key=%s, note=%s, expiry_notified_at='' WHERE id=%s""",
                    (d.get("name",""), d.get("vendor",""), d.get("vendor_email","").strip() if d.get("vendor_email") else "",
                     d.get("type",""), d.get("start_date",""), d.get("end_date",""),
                     float(d.get("cost") or 0), d.get("billing_period") or "One-Time", tag, d.get("asset_id") or None, d.get("employee_id") or "",
                     d.get("location") or "", d.get("department") or "", d.get("license_key") or "", d.get("note",""), cid))
        c.commit(); c.close()
        new_emp = (d.get("employee_id") or "").strip()
        if new_emp and new_emp != (old.get("employee_id") or "").strip():
            notify_person_contract_assigned(new_emp, d)
        return jsonify({"ok": True})
    cid = (request.get_json(force=True) or {}).get("id")
    cur.execute("UPDATE Contracts SET is_deleted=1 WHERE id=%s", [cid]); c.commit(); c.close(); return jsonify({"ok": True})

@app.route("/api/contracts/trash")
@auth_required(module="contracts", level="read")
def contracts_trash():
    c = conn(); cur = c.cursor()
    cur.execute("SELECT * FROM Contracts WHERE is_deleted=1 ORDER BY end_date"); rows = cur.fetchall(); c.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/contracts/<int:cid>/restore", methods=["POST"])
@auth_required(module="contracts", level="write")
def restore_contract(cid):
    c = conn(); cur = c.cursor()
    cur.execute("UPDATE Contracts SET is_deleted=0 WHERE id=%s", [cid]); c.commit(); c.close()
    return jsonify({"ok": True})

@app.route("/api/contracts/<int:cid>/permanent", methods=["DELETE"])
@auth_required(module="contracts", level="write")
def permanent_delete_contract(cid):
    c = conn(); cur = c.cursor()
    cur.execute("SELECT id FROM Contracts WHERE id=%s AND is_deleted=1", [cid])
    if not cur.fetchone():
        c.close(); return jsonify({"error": "not found in trash"}), 404
    cur.execute("DELETE FROM Contracts WHERE id=%s", [cid]); c.commit(); c.close()
    audit(session.get("user"), "PERMANENT_DELETE_CONTRACT", "", f"contract #{cid}")
    return jsonify({"ok": True})

@app.route("/api/contracts/trash/empty", methods=["POST"])
@auth_required(module="contracts", level="write")
def empty_contracts_trash():
    c = conn(); cur = c.cursor()
    cur.execute("SELECT id FROM Contracts WHERE is_deleted=1"); rows = cur.fetchall()
    cur.execute("DELETE FROM Contracts WHERE is_deleted=1")
    c.commit(); c.close()
    audit(session.get("user"), "EMPTY_CONTRACTS_TRASH", "", f"{len(rows)} contract(s) permanently deleted")
    return jsonify({"ok": True, "deleted": len(rows)})

@app.route("/api/locations", methods=["GET","POST","DELETE"])
@feature_required("directory.reflists")
def locations_api():
    c = conn(); cur = c.cursor()
    if request.method == "GET":
        cur.execute("SELECT * FROM Locations ORDER BY name"); rows = cur.fetchall(); c.close()
        return jsonify([dict(r) for r in rows])
    if request.method == "POST":
        d = request.get_json(force=True)
        cur.execute("INSERT IGNORE INTO Locations (name, parent_id) VALUES (%s,%s)", (d.get("name","").strip(), int(d.get("parent_id") or 0)))
        c.commit(); c.close(); return jsonify({"ok": True})
    lid = (request.get_json(force=True) or {}).get("id")
    cur.execute("DELETE FROM Locations WHERE id=%s", [lid]); c.commit(); c.close(); return jsonify({"ok": True})

# ---------- ticketing (osTicket-style) ----------
PRIORITIES = ["Low", "Normal", "High", "Urgent", "Emergency"]
TICKET_STATUSES = ["Open", "In Progress", "Pending", "Resolved", "Closed"]
TICKET_CATEGORIES = ["Hardware", "Software", "Network", "Access/Permissions", "Email/Communication", "Printer", "CCTV/Security", "Other"]

def ticket_code():
    return "TK-" + datetime.now().strftime("%Y%m%d") + "-" + secrets.token_hex(3).upper()

def sla_hours_for(priority):
    """Return SLA hours based on priority and Settings policy."""
    c = conn(); cur = c.cursor()
    cur.execute("SELECT sla_low, sla_normal, sla_high, sla_urgent FROM Settings WHERE id=1")
    s = cur.fetchone() or {}
    c.close()
    mapping = {"Low": s.get("sla_low", 72), "Normal": s.get("sla_normal", 24), "High": s.get("sla_high", 8), "Urgent": s.get("sla_urgent", 4), "Emergency": 2}
    return mapping.get(priority, 24)

def auto_assign_ticket(category):
    """Round-robin auto-assignment based on category. Returns username or None."""
    c = conn(); cur = c.cursor()
    cur.execute("SELECT auto_assign_roundrobin FROM Settings WHERE id=1")
    s = cur.fetchone() or {}
    if not s.get("auto_assign_roundrobin"):
        c.close(); return None
    # Get users with role admin or read-write (editor)
    cur.execute("SELECT username FROM Users WHERE role IN (%s,%s) ORDER BY username", (ROLE_ADMIN, ROLE_EDIT))
    users = [r["username"] for r in cur.fetchall()]
    if not users:
        c.close(); return None
    # Round-robin: assign to user with fewest open tickets
    cur.execute("SELECT assignee, COUNT(*) AS cnt FROM Tickets WHERE status IN ('Open','In Progress') AND assignee IS NOT NULL GROUP BY assignee")
    counts = {r["assignee"]: r["cnt"] for r in cur.fetchall()}
    c.close()
    users.sort(key=lambda u: counts.get(u, 0))
    return users[0]

def notify_ticket_created(ticket):
    """Notify admins/editors when a new ticket is created."""
    c = conn(); cur = c.cursor()
    cur.execute("SELECT notify_on_create FROM Settings WHERE id=1")
    s = cur.fetchone() or {}
    if not s.get("notify_on_create", 1):
        c.close(); return
    c.close()
    try:
        send_notification(f"New Ticket: {ticket['code']}", f"A new ticket has been created.\n\nCode: {ticket['code']}\nSubject: {ticket.get('subject','')}\nPriority: {ticket.get('priority','')}\nRequester: {ticket.get('requester','')}\nCategory: {ticket.get('category','')}\n\nLogin to view and assign.")
    except Exception as e:
        print("notify created error:", e)

def notify_requester_ticket_created(ticket):
    """Confirms to the requester (not staff) that their ticket was received,
    with the ticket code they need for the public status-lookup portal."""
    to = (ticket.get("requester_email") or "").strip()
    if not to:
        return
    bn = brand_name()
    body = (f"Your support ticket has been received.\n\n"
            f"Ticket ID: {ticket['code']}\n"
            f"Subject: {ticket.get('subject','')}\n"
            f"Priority: {ticket.get('priority','')}\n\n"
            f"Keep this Ticket ID -- you can check its status any time using it, "
            f"and we'll email you again when the status changes.")
    try:
        _send_simple_email(to, f"Ticket {ticket['code']} received", body)
    except Exception as e:
        print("notify requester created error:", e)

def notify_requester_status_changed(ticket, new_status):
    """Fires on ANY status change, not just Resolved -- separate from
    notify_ticket_resolved's specific wording, kept for that one case."""
    to = (ticket.get("requester_email") or "").strip()
    if not to:
        return
    body = (f"Your ticket's status has changed.\n\n"
            f"Ticket ID: {ticket.get('code','')}\n"
            f"Subject: {ticket.get('subject','')}\n"
            f"New Status: {new_status}\n")
    try:
        _send_simple_email(to, f"Ticket {ticket.get('code','')} status: {new_status}", body)
    except Exception as e:
        print("notify status change error:", e)

def notify_ticket_resolved(ticket):
    """Notify requester when a ticket is resolved/closed."""
    c = conn(); cur = c.cursor()
    cur.execute("SELECT notify_on_resolve FROM Settings WHERE id=1")
    s = cur.fetchone() or {}
    if not s.get("notify_on_resolve", 1):
        c.close(); return
    c.close()
    if not ticket.get("requester_email"):
        return
    try:
        import smtplib
        from email.message import EmailMessage
        c = conn(); cur = c.cursor()
        cur.execute("SELECT * FROM Settings WHERE id=1"); settings = cur.fetchone() or {}
        c.close()
        if not settings.get("smtp_host"):
            return
        bn = settings.get("app_name") or "IT-Vault"
        subj = f"{bn}: Ticket {ticket['code']} Resolved"
        body = (f"Your ticket has been resolved.\n\nCode: {ticket['code']}\nSubject: {ticket.get('subject','')}\nStatus: {ticket.get('status','')}\n\nIf you need further assistance, reply to this email or submit a new ticket.")
        msg = EmailMessage(); msg["Subject"] = subj
        msg["From"] = settings.get("smtp_from") or settings.get("smtp_user")
        msg["To"] = ticket["requester_email"]; msg.set_content(body + _email_footer(bn))
        with smtplib.SMTP(settings["smtp_host"], int(settings.get("smtp_port", 587) or 587), timeout=10) as sv:
            if settings.get("smtp_user"): sv.starttls(); sv.login(settings["smtp_user"], settings.get("smtp_pass", ""))
            sv.send_message(msg)
    except Exception as e:
        print("notify resolved error:", e)

def notify_ticket_replied(ticket, reply_author, reply_body):
    """Notify requester when their ticket gets a reply."""
    c = conn(); cur = c.cursor()
    cur.execute("SELECT notify_on_reply FROM Settings WHERE id=1")
    s = cur.fetchone() or {}
    if not s.get("notify_on_reply", 1):
        c.close(); return
    c.close()
    if not ticket.get("requester_email"):
        return
    try:
        import smtplib
        from email.message import EmailMessage
        c = conn(); cur = c.cursor()
        cur.execute("SELECT * FROM Settings WHERE id=1"); settings = cur.fetchone() or {}
        c.close()
        if not settings.get("smtp_host"):
            return
        bn = settings.get("app_name") or "IT-Vault"
        subj = f"{bn}: Reply on Ticket {ticket['code']}"
        body = (f"Your ticket received a reply.\n\nCode: {ticket['code']}\nSubject: {ticket.get('subject','')}\nReply from: {reply_author}\n\n{reply_body[:500]}\n\nLogin to view full thread.")
        msg = EmailMessage(); msg["Subject"] = subj
        msg["From"] = settings.get("smtp_from") or settings.get("smtp_user")
        msg["To"] = ticket["requester_email"]; msg.set_content(body + _email_footer(bn))
        with smtplib.SMTP(settings["smtp_host"], int(settings.get("smtp_port", 587) or 587), timeout=10) as sv:
            if settings.get("smtp_user"): sv.starttls(); sv.login(settings["smtp_user"], settings.get("smtp_pass", ""))
            sv.send_message(msg)
    except Exception as e:
        print("notify replied error:", e)

def check_sla_breach(ticket):
    """Check if a ticket has breached SLA. Returns True if overdue."""
    if not ticket.get("due_date"):
        return False
    if ticket.get("status") in ("Resolved", "Closed"):
        return False
    try:
        from datetime import datetime
        due = datetime.strptime(ticket["due_date"], "%Y-%m-%d %H:%M:%S")
        return datetime.now() > due
    except Exception:
        return False

@app.route("/api/tickets", methods=["GET","POST"])
@auth_required(module="tickets", level="read")
def tickets_api():
    if request.method != "GET" and not _module_write_allowed("tickets"):
        return jsonify({"error": "No access"}), 403
    c = conn(); cur = c.cursor()
    if request.method == "GET":
        q = request.args.get("q","").strip(); st = request.args.get("status","")
        sql = "SELECT t.*, (SELECT COUNT(*) FROM TicketReplies r WHERE r.ticket_id=t.id) AS reply_count FROM Tickets t"
        where=[]; params=[]
        if st: where.append("t.status=%s"); params.append(st)
        if q:
            where.append("(t.subject LIKE %s OR t.code LIKE %s OR t.requester LIKE %s OR t.assignee LIKE %s)")
            params += [f"%{q}%"]*4
        if where: sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY (t.status IN ('Open','In Progress')) DESC, t.updated_at DESC"
        cur.execute(sql, params); rows = cur.fetchall(); c.close()
        return jsonify([dict(r) for r in rows])
    # POST: create ticket
    d = request.get_json(force=True)
    subject = d.get("subject","").strip()
    requester = d.get("requester","")
    description = d.get("description","")
    # guard against accidental double-submit (e.g. a fast double-click) --
    # if the exact same ticket was just created seconds ago, return it
    # instead of inserting a duplicate
    cur.execute("""SELECT id, code FROM Tickets WHERE subject=%s AND requester=%s AND description=%s
                   AND created_at > NOW() - INTERVAL 15 SECOND ORDER BY id DESC LIMIT 1""",
                (subject, requester, description))
    dup = cur.fetchone()
    if dup:
        c.close()
        return jsonify({"ok": True, "id": dup["id"], "code": dup["code"]})
    code = ticket_code()
    priority = d.get("priority","Normal") or "Normal"
    category = d.get("category","") or ""
    sla_hours = int(d.get("sla_hours") or sla_hours_for(priority))
    # auto-assign if round-robin enabled and no assignee specified
    assignee = d.get("assignee") or None
    if not assignee:
        assignee = auto_assign_ticket(category)
    # auto due_date from SLA hours if not specified
    due_date = d.get("due_date","") or ""
    if not due_date:
        from datetime import datetime, timedelta
        due_date = (datetime.now() + timedelta(hours=sla_hours)).strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("""INSERT INTO Tickets (code, subject, description, priority, status, requester, requester_email, assignee, asset_id, due_date, sla_hours, category, source, created_by)
                   VALUES (%s,%s,%s,%s,'Open',%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (code, subject, description, priority,
                 requester, d.get("requester_email",""), assignee, d.get("asset_id") or None,
                 due_date, sla_hours, category, d.get("source","Web"), session.get("user","?")))
    tid = cur.lastrowid
    c.commit(); c.close()
    # notify after commit
    ticket = {"id": tid, "code": code, "subject": d.get("subject",""), "priority": priority, "requester": d.get("requester",""), "requester_email": d.get("requester_email",""), "category": category}
    try: notify_ticket_created(ticket)
    except Exception as e: print("notify created error:", e)
    notify_requester_ticket_created(ticket)
    return jsonify({"ok": True, "id": tid, "code": code})

@app.route("/api/portal/tickets", methods=["POST"])
def portal_create_ticket():
    """Public (no auth) ticket/request intake from the portal invite link.

    Accepts JSON, or multipart/form-data when the visitor attached photos.
    Photos ride along with the ticket they belong to rather than going through
    an attach-by-code endpoint of their own, so this stays the single public
    write and nobody can staple a file onto someone else's ticket.

    get_json(force=True) must NOT be reached for a multipart body: it raises
    a 400 that reads as "the browser sent a request this server could not
    understand", which is what every photo upload got.
    """
    if (request.content_type or "").startswith("multipart/form-data"):
        d = {k: v for k, v in request.form.items()}
        photos = request.files.getlist("photos")
    else:
        d = request.get_json(force=True) or {}
        photos = []
    subject = (d.get("subject") or "").strip()
    description = (d.get("description") or "").strip()
    if not subject or not description:
        return jsonify({"error": "subject and description required"}), 400
    # optional token gate
    c = conn(); cur = c.cursor()
    cur.execute("SELECT portal_token FROM Settings WHERE id=1"); srow = cur.fetchone() or {}
    token = (d.get("token") or "").strip()
    if srow.get("portal_token") and token != srow["portal_token"]:
        c.close(); return jsonify({"error": "invalid or missing token"}), 403
    requester = (d.get("requester") or "").strip()
    cur.execute("""SELECT id, code FROM Tickets WHERE subject=%s AND requester=%s AND description=%s
                   AND created_at > NOW() - INTERVAL 15 SECOND ORDER BY id DESC LIMIT 1""",
                (subject, requester, description))
    dup = cur.fetchone()
    if dup:
        # A double-tapped submit button lands here. The ticket already exists,
        # so attach the photos to it rather than losing them.
        saved, skipped = 0, []
        if photos:
            try:
                saved, skipped = _store_ticket_photos(cur, dup["id"], photos, "portal")
                c.commit()
            except Exception as e:
                print("portal photo error:", e)
        c.close()
        return jsonify({"ok": True, "id": dup["id"], "code": dup["code"],
                        "photos": saved, "photo_warnings": skipped})
    code = ticket_code()
    priority = (d.get("priority") or "Normal") or "Normal"
    category = d.get("category","") or ""
    sla_hours = sla_hours_for(priority)
    assignee = auto_assign_ticket(category)
    from datetime import datetime, timedelta
    due_date = (datetime.now() + timedelta(hours=sla_hours)).strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("""INSERT INTO Tickets (code, subject, description, priority, status, requester, requester_email, assignee, due_date, sla_hours, category, source, created_by)
                   VALUES (%s,%s,%s,%s,'Open',%s,%s,%s,%s,%s,%s,'Portal','portal')""",
                (code, subject, description, priority,
                 requester, (d.get("requester_email") or "").strip(),
                 assignee, due_date, sla_hours, category))
    tid = cur.lastrowid
    # A photo that fails validation must not cost the visitor their ticket --
    # the text is the part nobody can reconstruct, so it is committed either
    # way and the rejected files come back as warnings.
    saved, skipped = 0, []
    if photos:
        try:
            saved, skipped = _store_ticket_photos(cur, tid, photos, "portal")
        except Exception as e:
            print("portal photo error:", e)
            skipped.append("photos could not be saved")
    c.commit(); c.close()
    ticket = {"id": tid, "code": code, "subject": subject, "priority": priority, "requester": d.get("requester",""), "requester_email": d.get("requester_email",""), "category": category}
    try: notify_ticket_created(ticket)
    except Exception as e: print("notify created error:", e)
    notify_requester_ticket_created(ticket)
    return jsonify({"ok": True, "code": code, "id": tid,
                    "photos": saved, "photo_warnings": skipped})

@app.route("/portal")
def portal_page():
    return send_from_directory(BASE, "portal.html")

@app.route("/monitor")
@auth_required()
def monitor_page():
    return send_from_directory(BASE, "monitor.html")

@app.route("/api/portal/link")
@auth_required([ROLE_ADMIN, ROLE_EDIT])
def portal_link():
    """Returns the public portal URL (with token if configured)."""
    c = conn(); cur = c.cursor()
    cur.execute("SELECT portal_token, app_name FROM Settings WHERE id=1"); s = cur.fetchone() or {}
    c.close()
    base = request.host_url.rstrip("/")
    url = base + "/portal"
    if s.get("portal_token"):
        url += "?t=" + s["portal_token"]
    return jsonify({"url": url, "token": s.get("portal_token") or "", "app_name": s.get("app_name") or "IT-Vault"})

@app.route("/api/portal/status", methods=["POST"])
def portal_status():
    """Public ticket status lookup by code only."""
    d = request.get_json(force=True) or {}
    code = (d.get("code") or "").strip().upper()
    if not code:
        return jsonify({"error": "Ticket code required"}), 400
    c = conn(); cur = c.cursor()
    cur.execute("SELECT * FROM Tickets WHERE code=%s", [code])
    t = cur.fetchone()
    if not t:
        c.close(); return jsonify({"error": "Ticket not found. Check the code."}), 404
    cur.execute("SELECT * FROM TicketReplies WHERE ticket_id=%s ORDER BY created_at", [t["id"]])
    reps = cur.fetchall()
    atts = _attachment_rows(cur, t["id"])
    c.close()
    return jsonify({"ticket": dict(t), "replies": [dict(r) for r in reps], "attachments": atts})

@app.route("/api/tickets/<int:ticket_id>", methods=["GET","PUT","DELETE"])
@auth_required(module="tickets", level="read")
def ticket_detail(ticket_id):
    if request.method != "GET" and not _module_write_allowed("tickets"):
        return jsonify({"error": "No access"}), 403
    # Deleting a ticket destroys its replies and its trail, so that is
    # admin-only outright.
    if request.method == "DELETE" and not _feature_allowed("tickets.delete"):
        return jsonify({"error": "No access -- you can't delete a ticket"}), 403
    # Editing a ticket's content is admin-only, but working the queue is not:
    # moving status and priority is what anyone with tickets write does every
    # day (the reply box sends exactly that), so those two stay open and only
    # the rest of the fields need admin. Both paths are recorded in the trail.
    if request.method == "PUT":
        # Assigning is queue work too -- there is a dedicated "Assign to IT"
        # control for it -- so it sits with status and priority.
        _queue_only = {"status", "priority", "assignee"}
        _touched = {k for k in (request.get_json(silent=True) or {}).keys()}
        if not _touched.issubset(_queue_only) and not _feature_allowed("tickets.edit"):
            return jsonify({"error": "No access -- you can't change a ticket's details. "
                                     "You can still reply, and set status and priority."}), 403
    c = conn(); cur = c.cursor()
    if request.method == "GET":
        cur.execute("SELECT * FROM Tickets WHERE id=%s", [ticket_id]); t = cur.fetchone()
        if not t: c.close(); return jsonify({"error":"not found"}), 404
        cur.execute("SELECT * FROM TicketReplies WHERE ticket_id=%s ORDER BY created_at", [ticket_id]); reps = cur.fetchall()
        atts = _attachment_rows(cur, ticket_id)
        c.close()
        return jsonify({"ticket": dict(t), "replies": [dict(r) for r in reps], "attachments": atts})
    if request.method == "PUT":
        d = request.get_json(force=True)
        # fetch current to detect changes
        cur.execute("SELECT * FROM Tickets WHERE id=%s", [ticket_id]); before = cur.fetchone() or {}
        fields = []
        params = []
        for f in ["subject","description","priority","status","requester","requester_email","assignee","asset_id","due_date","sla_hours","category"]:
            if f in d:
                fields.append(f"{f}=%s"); params.append(None if (d[f] in ("", None) and f in ("assignee","asset_id")) else d[f])
        if d.get("status") in ("Resolved","Closed") and not d.get("closed_at"):
            fields.append("closed_at=NOW()")
        if fields:
            params.append(ticket_id)
            cur.execute("UPDATE Tickets SET "+", ".join(fields)+", updated_at=NOW() WHERE id=%s", params)
        # One row per field that actually changed, so the ticket view can show
        # the same "who changed what, when" trail an asset has. Compared against
        # the pre-update snapshot, and only written when the value really moved.
        who = session.get("user") or "?"
        for fname in ["subject", "description", "priority", "status", "requester",
                      "requester_email", "assignee", "asset_id", "due_date",
                      "sla_hours", "category"]:
            if fname not in d:
                continue
            was = "" if (before or {}).get(fname) is None else str((before or {}).get(fname))
            now = "" if d[fname] is None else str(d[fname])
            if was.strip() == now.strip():
                continue
            _ticket_hist(cur, ticket_id, who, fname, was, now)
        c.commit(); c.close()
        # notify on assignment change
        new_assignee = d.get("assignee")
        if new_assignee and new_assignee != (before.get("assignee") or ""):
            try: notify_ticket_assigned(dict(before), new_assignee)
            except Exception as e: print("assign notify call error:", e)
        # notify requester on ANY status change -- merged reflects the actual
        # new state (before was fetched pre-update, so it still has the old status)
        new_status = d.get("status")
        old_status = before.get("status")
        if new_status and new_status != old_status:
            merged = {**dict(before), **d}
            if new_status in ("Resolved", "Closed"):
                try: notify_ticket_resolved(merged)
                except Exception as e: print("resolve notify error:", e)
            else:
                notify_requester_status_changed(merged, new_status)
        return jsonify({"ok": True})
    cur.execute("DELETE FROM Tickets WHERE id=%s", [ticket_id])
    cur.execute("DELETE FROM TicketReplies WHERE ticket_id=%s", [ticket_id])
    c.commit(); c.close(); return jsonify({"ok": True})

@app.route("/api/tickets/<int:ticket_id>/history")
@auth_required(module="tickets", level="read")
def ticket_history(ticket_id):
    """Same shape as /api/assets/<id>/history, so the UI renders it the same."""
    c = conn(); cur = c.cursor()
    cur.execute("SELECT ts, user, field, old_val, new_val FROM TicketHistory "
                "WHERE ticket_id=%s ORDER BY ts DESC", [ticket_id])
    rows = cur.fetchall(); c.close()
    return jsonify([{"ts": str(r["ts"]), "user": r["user"], "field": r["field"],
                     "old_val": r["old_val"], "new_val": r["new_val"]} for r in rows])

@app.route("/api/tickets/<int:ticket_id>/attachments", methods=["GET", "POST"])
@auth_required(module="tickets", level="read")
def ticket_attachments(ticket_id):
    """Metadata for a ticket's photos, and a way for an agent to add more.

    Adding is queue work -- an engineer photographing the repair belongs in
    the same bucket as replying -- so it needs tickets write, not admin.
    """
    if request.method == "POST" and not _feature_allowed("tickets.photos"):
        return jsonify({"error": "No access -- you can't add photos"}), 403
    c = conn(); cur = c.cursor()
    if request.method == "POST":
        files = request.files.getlist("photos") or request.files.getlist("file")
        if not files:
            c.close(); return jsonify({"error": "no file"}), 400
        saved, skipped = _store_ticket_photos(cur, ticket_id, files,
                                              session.get("user") or "agent")
        if saved:
            _ticket_hist(cur, ticket_id, session.get("user") or "agent",
                         "attachment", "", f"added {saved} photo(s)")
        c.commit()
        rows = _attachment_rows(cur, ticket_id)
        c.close()
        return jsonify({"ok": True, "saved": saved, "warnings": skipped, "attachments": rows})
    rows = _attachment_rows(cur, ticket_id)
    c.close()
    return jsonify(rows)


@app.route("/api/tickets/<int:ticket_id>/attachments/<int:att_id>", methods=["GET", "DELETE"])
@auth_required(module="tickets", level="read")
def ticket_attachment_one(ticket_id, att_id):
    """Serve or remove one photo. Deleting destroys evidence, so it is
    admin-only, like deleting the ticket itself."""
    if request.method == "DELETE" and not _feature_allowed("tickets.delete"):
        return jsonify({"error": "No access -- you can't delete a photo"}), 403
    c = conn(); cur = c.cursor()
    if request.method == "DELETE":
        cur.execute("SELECT filename FROM TicketAttachments WHERE id=%s AND ticket_id=%s",
                    (att_id, ticket_id))
        row = cur.fetchone()
        if not row:
            c.close(); return jsonify({"error": "not found"}), 404
        cur.execute("DELETE FROM TicketAttachments WHERE id=%s AND ticket_id=%s", (att_id, ticket_id))
        _ticket_hist(cur, ticket_id, session.get("user") or "agent",
                     "attachment", row.get("filename") or "photo", "deleted")
        c.commit(); c.close()
        return jsonify({"ok": True})
    cur.execute("""SELECT filename, mimetype, data FROM TicketAttachments
                   WHERE id=%s AND ticket_id=%s""", (att_id, ticket_id))
    row = cur.fetchone(); c.close()
    if not row or not row.get("data"):
        return jsonify({"error": "not found"}), 404
    return _attachment_response(row)


@app.route("/api/portal/attachments/<code>/<int:att_id>")
def portal_attachment(code, att_id):
    """Public read of a photo, gated on the ticket code.

    The code is already the only thing standing between a visitor and their
    ticket in /api/portal/status, so this adds no new exposure -- but the
    photo is still reachable only through the ticket it was attached to.
    """
    c = conn(); cur = c.cursor()
    cur.execute("""SELECT a.filename, a.mimetype, a.data
                   FROM TicketAttachments a JOIN Tickets t ON t.id = a.ticket_id
                   WHERE t.code=%s AND a.id=%s""", ((code or "").strip().upper(), att_id))
    row = cur.fetchone(); c.close()
    if not row or not row.get("data"):
        return jsonify({"error": "not found"}), 404
    return _attachment_response(row)


@app.route("/api/tickets/<int:ticket_id>/reply", methods=["POST"])
# read, not write: a role with tickets='none' is correctly shut out, but
# gating this at write would silently take replying away from built-in
# read-only staff, who legitimately answer on their own helpdesk threads.
@auth_required(module="tickets", level="read")
def ticket_reply(ticket_id):
    d = request.get_json(force=True)
    body = (d.get("body") or "").strip()
    if not body: return jsonify({"error":"empty"}), 400
    c = conn(); cur = c.cursor()
    role = "agent" if session.get("role") in (ROLE_ADMIN, ROLE_EDIT) else "requester"
    cur.execute("INSERT INTO TicketReplies (ticket_id, author, author_role, body) VALUES (%s,%s,%s,%s)",
                (ticket_id, session.get("user","?"), role, body))
    # auto reopen if was closed/resolved
    cur.execute("UPDATE Tickets SET status='In Progress', updated_at=NOW() WHERE id=%s AND status IN ('Resolved','Closed')", [ticket_id])
    # fetch ticket for notification
    cur.execute("SELECT * FROM Tickets WHERE id=%s", [ticket_id]); ticket = cur.fetchone() or {}
    c.commit(); c.close()
    # notify requester of reply
    try: notify_ticket_replied(dict(ticket), session.get("user","agent"), body)
    except Exception as e: print("reply notify error:", e)
    return jsonify({"ok": True})

# ---------- branding (public, no auth) ----------
@app.route("/api/ldap/test", methods=["POST"])
@auth_required(module="settings", level="write")
def ldap_test():
    d = request.get_json(force=True)
    row = {
        "ldap_server": (d.get("ldap_server") or "").strip(),
        "ldap_bind_user": (d.get("ldap_bind_user") or "").strip(),
        "ldap_bind_pass": d.get("ldap_bind_pass") or "",
        "ldap_base_dn": (d.get("ldap_base_dn") or "").strip(),
    }
    if not row["ldap_server"] or not row["ldap_bind_user"] or not row["ldap_bind_pass"]:
        return jsonify({"ok": False, "error": "Fill server, bind user and password"}), 400
    try:
        import ldap3
        conn = _ldap_connect(row, get_info=ldap3.NONE)
        ok = conn.bound
        # try a base search to confirm directory reachable
        if row["ldap_base_dn"]:
            try:
                conn.search(row["ldap_base_dn"], "(objectClass=*)", search_scope="BASE",
                            attributes=["defaultNamingContext"])
            except Exception:
                pass
        conn.unbind()
        if ok:
            return jsonify({"ok": True, "msg": "Connected to Domain Controller"})
        return jsonify({"ok": False, "error": "Bind failed (check credentials / account disabled)"}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:300]}), 400

@app.route("/api/branding")
def branding():
    c = conn(); cur = c.cursor()
    cur.execute("SELECT app_name, logo_text, matrix_on, theme, theme_preset, bg_type, bg, comp_bg, radius, font, accent, accent2, language, currency, company_phone, company_address FROM Settings WHERE id=1"); s = cur.fetchone(); c.close()
    s = s or {}
    return jsonify({"app_name": s.get("app_name", "IT-Vault"), "logo_text": s.get("logo_text", "IT-Vault"),
                    "matrix_on": bool(s.get("matrix_on", 1)), "logo": "/logo.png",
                    "theme": s.get("theme", "dark"), "theme_preset": s.get("theme_preset", "deepdark"),
                    "bg_type": s.get("bg_type", "solid"), "bg": s.get("bg", "#0a0d13"),
                    "comp_bg": s.get("comp_bg", "#121826"), "radius": s.get("radius", 12),
                    "font": s.get("font", "Rajdhani"), "accent": s.get("accent", "#ff3b30"),
                    "accent2": s.get("accent2", "#c0392b"), "language": s.get("language", "en"),
                    "currency": s.get("currency", "AED"),
                    "company_phone": s.get("company_phone", ""), "company_address": s.get("company_address", "")})

@app.route("/api/logo", methods=["POST"])
@auth_required(module="settings", level="write")
def upload_logo():
    if "file" not in request.files:
        return jsonify({"error": "no file"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "no file"}), 400
    data = f.read(24 * 1024 * 1024 + 1)
    if len(data) > 24 * 1024 * 1024:
        return jsonify({"error": "that file is over 24MB -- please use a smaller one"}), 400
    if not _sniff_image(data)[0]:
        return jsonify({"error": "that file isn't a PNG, JPEG, GIF, WebP or HEIC image"}), 400
    data = _fit_png(data, LOGO_MAX_EDGE, LOGO_MAX_BYTES)
    # Database first: the file is a cache that a container replacement takes
    # with it, which is how branding used to disappear on update.
    ok, err = _brand_store("logo", LOGO_PATH, data)
    if not ok:
        return jsonify({"error": err or "could not save the logo"}), 500
    return jsonify({"ok": True, "logo": "/logo.png"})

@app.route("/logo.png")
def logo_file():
    sent = _brand_send("logo", LOGO_PATH, "logo.png")
    if sent is not None:
        return sent
    # no custom logo uploaded yet (fresh install, or right after a wipe) --
    # show the real IT-Vault shield mark instead of a blank/broken image,
    # until an admin uploads their own.
    return send_from_directory(BASE, "default_logo.png")

def _logo_data_uri():
    """Logo as a data: URI for embedding straight into a print/PDF: the
    uploaded blob if there is one, else the on-disk logo.png if it's not
    just the empty placeholder a wipe leaves behind, else the bundled
    IT-Vault shield mark -- so a fresh/wiped instance still prints a real
    logo instead of a blank box."""
    import base64
    try:
        lc = conn(); lcur = lc.cursor()
        lcur.execute("SELECT logo FROM Settings WHERE id=1"); lr = lcur.fetchone(); lc.close()
        if lr and lr.get("logo"):
            return "data:image/png;base64," + base64.b64encode(lr["logo"]).decode("ascii")
    except Exception:
        pass
    for fname in ("logo.png", "default_logo.png"):
        try:
            p = os.path.join(BASE, fname)
            if os.path.getsize(p) > 0:
                with open(p, "rb") as fp:
                    return "data:image/png;base64," + base64.b64encode(fp.read()).decode("ascii")
        except Exception:
            continue
    return ""

# ---------- email notifications ----------
def brand_name():
    try:
        c = conn(); cur = c.cursor()
        cur.execute("SELECT app_name FROM Settings WHERE id=1"); r = cur.fetchone(); c.close()
        return (r.get("app_name") or "IT-Vault") if r else "IT-Vault"
    except Exception:
        return "IT-Vault"
def _lookup_person_email(identifier):
    """Resolve either a system Users.username or an Employees.EmployeeID to
    an email address, since 'who this asset/contract is assigned to' can be
    either (checkout lets you pick from both). Empty string if none on file."""
    if not identifier:
        return ""
    c = conn(); cur = c.cursor()
    cur.execute("SELECT email FROM Users WHERE username=%s", [identifier])
    r = cur.fetchone()
    if r and r.get("email"):
        c.close(); return r["email"]
    cur.execute("SELECT Email FROM Employees WHERE EmployeeID=%s", [identifier])
    r = cur.fetchone(); c.close()
    return (r.get("Email") if r else "") or ""

def notify_person_asset_assigned(employee_id, asset, checked_out=False):
    """Emails the specific person an asset is assigned to (not the general
    staff broadcast) -- only Asset ID + Serial, never MAC, per policy. Includes
    a signature/acknowledgement link so they can sign for it directly from
    the email, without an admin having to separately generate and send one."""
    to = _lookup_person_email(employee_id)
    if not to:
        return False
    tag = asset.get("AssetTag") or asset.get("_id", "")
    name = (asset.get("Name") or "").strip()
    what = f"{tag} ({name})" if name else tag
    verb = "checked out to you" if checked_out else "assigned to you"
    lead = f"We have deployed asset {what} to you."
    ask = "Kindly review the details and acknowledge receipt by signing."
    body = f"{lead}\n"
    html_body = None
    aid = asset.get("_id")
    if aid:
        try:
            tk = _sign_token({"asset_id": aid, "name": asset.get("Name", "")}, exp_hours=168)
            sign_url = f"{request.host_url}sign?token={quote(tk)}"
            body += f"\n{ask}\n{sign_url}\n"
            html_body = _button_email_html(
                f"We have deployed asset <b>{tag}</b>{(' (' + name + ')') if name else ''} to you.<br>{ask}",
                "Review &amp; Sign Acknowledgement", sign_url)
        except Exception as e:
            print("sign link build error:", e)
    return _send_simple_email(to, f"Asset {verb}: {name or tag}", body, html_body=html_body)

def notify_asset_status_changed(asset, old_status, new_status):
    """Emails the assigned employee, whoever requested it, and every
    admin/staff account whenever an asset's Status changes -- e.g.
    Available -> Under-Maintenance or Checked-Out -> Retired, not just
    checkout/checkin."""
    if not new_status or new_status == old_status:
        return
    tag = asset.get("AssetTag") or asset.get("_id", "")
    subj = f"Asset status changed: {asset.get('Name','')}"
    body = (f"'{asset.get('Name','')}' (Asset ID: {tag}) status changed from "
            f"{old_status or '—'} to {new_status}.\n\n"
            f"Asset ID: {tag}\n"
            f"Serial Number: {asset.get('Serial') or '—'}\n")
    recipients = set()
    emp_email = _lookup_person_email(asset.get("EmployeeID") or "")
    if emp_email:
        _send_simple_email(emp_email, subj, body); recipients.add(emp_email.lower())
    req_email = _lookup_person_email(asset.get("RequestedBy") or "")
    if req_email and req_email.lower() not in recipients:
        _send_simple_email(req_email, subj, body); recipients.add(req_email.lower())
    try:
        c = conn(); cur = c.cursor()
        cur.execute("SELECT email FROM Users WHERE email<>''")
        admin_emails = [r["email"] for r in cur.fetchall()]
        c.close()
    except Exception:
        admin_emails = []
    for e in admin_emails:
        if e and e.lower() not in recipients:
            _send_simple_email(e, subj, body); recipients.add(e.lower())

def notify_person_contract_assigned(employee_id, contract):
    to = _lookup_person_email(employee_id)
    if not to:
        return False
    body = (f"A contract has been assigned to you.\n\n"
            f"Name: {contract.get('name','')}\n"
            f"Type: {contract.get('type','')}\n"
            f"Vendor: {contract.get('vendor') or '—'}\n"
            f"End Date: {contract.get('end_date') or '—'}\n")
    return _send_simple_email(to, f"Contract assigned to you: {contract.get('name','')}", body)

def _email_footer(app_name):
    """Small signature line appended to every outgoing email (notifications,
    OTP codes, alerts) -- keeps the sender's own brand name in the subject/body
    while still crediting the tool, unobtrusively, on its own short line."""
    return f"\n\n—\n{app_name} · Powered by Sha The IT Guy"
def send_notification(subject, body):
    import smtplib
    from email.message import EmailMessage
    c = conn(); cur = c.cursor()
    cur.execute("SELECT * FROM Settings WHERE id=1"); s = cur.fetchone() or {}
    cur.execute("SELECT email FROM Users WHERE email<>'' "); emails = [r["email"] for r in cur.fetchall()]
    c.close()
    if not s.get("smtp_host") or not emails:
        return False
    try:
        bn = s.get("app_name") or "IT-Vault"
        subj = subject if subject.startswith(bn) else f"{bn}: {subject}" if not subject.startswith("IT Guy") else subject.replace("IT Guy", bn, 1)
        msg = EmailMessage(); msg["Subject"] = subj; msg["From"] = s.get("smtp_from") or s.get("smtp_user")
        msg["To"] = ", ".join(emails); msg.set_content(body + _email_footer(bn))
        with smtplib.SMTP(s["smtp_host"], int(s.get("smtp_port", 587) or 587), timeout=10) as sv:
            if s.get("smtp_user"): sv.starttls(); sv.login(s["smtp_user"], s.get("smtp_pass", ""))
            sv.send_message(msg)
        return True
    except Exception as e:
        print("notify error:", e); return False

def notify_ticket_assigned(ticket, assignee_user):
    """Email the assignee + requester when a ticket is assigned. Returns True if sent."""
    import smtplib
    from email.message import EmailMessage
    c = conn(); cur = c.cursor()
    cur.execute("SELECT * FROM Settings WHERE id=1"); s = cur.fetchone() or {}
    # assignee email
    assignee_email = ""
    if assignee_user:
        cur.execute("SELECT email FROM Users WHERE username=%s", [assignee_user]); ur = cur.fetchone()
        if ur: assignee_email = ur.get("email") or ""
    c.close()
    if not s.get("smtp_host"):
        return False
    bn = s.get("app_name") or "IT-Vault"
    recipients = []
    if assignee_email: recipients.append(assignee_email)
    if ticket.get("requester_email"): recipients.append(ticket["requester_email"])
    if not recipients:
        return False
    try:
        subj = f"{bn}: Ticket {ticket['code']} assigned to {assignee_user or 'IT team'}"
        body = (f"Ticket: {ticket['code']}\n"
                f"Subject: {ticket.get('subject','')}\n"
                f"Priority: {ticket.get('priority','')}\n"
                f"Requester: {ticket.get('requester','')} ({ticket.get('requester_email','')})\n\n"
                f"This ticket has been assigned to {assignee_user or 'the IT team'}.\n"
                f"Login to {s.get('app_name') or 'IT-Vault'} to update status and reply.\n")
        msg = EmailMessage(); msg["Subject"] = subj
        msg["From"] = s.get("smtp_from") or s.get("smtp_user")
        msg["To"] = ", ".join(recipients); msg.set_content(body + _email_footer(bn))
        with smtplib.SMTP(s["smtp_host"], int(s.get("smtp_port", 587) or 587), timeout=10) as sv:
            if s.get("smtp_user"): sv.starttls(); sv.login(s["smtp_user"], s.get("smtp_pass", ""))
            sv.send_message(msg)
        return True
    except Exception as e:
        print("assign notify error:", e); return False

@app.route("/api/settings/smtp-test", methods=["POST"])
@auth_required(module="settings", level="write")
def test_email():
    import smtplib
    from email.message import EmailMessage
    d = request.get_json(force=True) or {}
    c = conn(); cur = c.cursor()
    cur.execute("SELECT smtp_host, smtp_port, smtp_user, smtp_pass, smtp_from, app_name FROM Settings WHERE id=1")
    cur0 = cur.fetchone() or {}
    cur.execute("SELECT email FROM Users WHERE username=%s", [session.get("user")])
    ur = cur.fetchone() or {}
    c.close()
    def gv(k, fb=""):
        v = d.get(k)
        return v if v not in (None, "") else cur0.get(k, fb)
    host = (gv("smtp_host") or "").strip()
    if not host:
        return jsonify({"ok": False, "error": "SMTP host not set"}), 400
    port = int(gv("smtp_port", 587) or 587)
    user = (gv("smtp_user") or "").strip()
    pw = gv("smtp_pass")
    frm = (gv("smtp_from") or user).strip()
    to = (ur.get("email") or "").strip() or frm
    if not to:
        return jsonify({"ok": False, "msg": "No address to send the test to -- set your own email on your profile, or an SMTP From address"}), 400
    try:
        bn = (gv("app_name") or "IT-Vault").strip() or "IT-Vault"
        msg = EmailMessage()
        msg["Subject"] = f"{bn} · SMTP check ✅"
        msg["From"] = frm
        msg["To"] = to
        msg.set_content(
            f"Yo — this is your SMTP test email from {bn}.\n\n"
            "If it landed in your inbox, your setup is locked in and ready to send "
            "real notifications. No cap. \U0001F680\n\n"
            "Nothing else to do here — you're good to go." + _email_footer(bn)
        )
        with smtplib.SMTP(host, port, timeout=10) as sv:
            if user:
                sv.starttls(); sv.login(user, pw or "")
            sv.send_message(msg)
        return jsonify({"ok": True, "msg": f"Sent to {to}"})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 400

# ---------- audit helper ----------
def audit(actor, action, asset_id, detail):
    try:
        c = conn(); cur = c.cursor()
        cur.execute("INSERT INTO AuditLog (actor, action, asset_id, detail) VALUES (%s,%s,%s,%s)",
                    (actor, action, asset_id, detail))
        c.commit(); c.close()
    except Exception as e:
        print("audit error:", e)

def nowstr():
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M")

# ---------- ITAM: checkout / checkin ----------
@app.route("/api/assets/<a_id>/checkout", methods=["POST"])
@auth_required(module="assets", level="write")
def checkout_asset(a_id):
    d = request.get_json(force=True)
    user = (d.get("username") or "").strip()
    if not user: return jsonify({"error": "username required"}), 400
    expected = (d.get("expected") or "").strip()
    note = (d.get("note") or "").strip()
    # "Signed Date" is only ever set here (at the moment of checkout), never
    # freely edited on the Asset form -- defaults to today, but the checkout
    # dialog lets you pick a different day if the sign-off happened earlier.
    signed_date = (d.get("signed_date") or "").strip() or datetime.now().strftime("%Y-%m-%d")
    c = conn(); cur = c.cursor()
    cur.execute("SELECT _id, Name FROM Assets WHERE _id=%s", [a_id]); a = cur.fetchone()
    if not a: c.close(); return jsonify({"error": "asset not found"}), 404
    cur.execute("UPDATE Assets SET Status='Checked-Out', ReceivedBy=%s, NotesReceived=%s WHERE _id=%s", (user, signed_date, a_id))
    cur.execute("INSERT INTO Checkouts (asset_id, username, checkout_date, expected_checkin, note) VALUES (%s,%s,%s,%s,%s)",
                (a_id, user, nowstr(), expected, note))
    c.commit(); c.close()
    audit(session.get("user"), "CHECKOUT", a_id, f"{a['Name']} -> {user}" + (f" (due {expected})" if expected else ""))
    send_notification("IT Guy: Asset checked out", f"'{a['Name']}' was checked out to {user} by {session.get('user')}.")
    try:
        cc = conn(); ccur = cc.cursor()
        ccur.execute("SELECT * FROM Assets WHERE _id=%s", [a_id]); full_asset = ccur.fetchone(); cc.close()
    except Exception:
        full_asset = None
    full_asset = full_asset or {"Name": a["Name"], "_id": a_id}
    notify_person_asset_assigned(user, full_asset, checked_out=True)
    try:
        notify_asset_status_changed(full_asset, None, "Checked-Out")
    except Exception as e:
        print("asset status-change notify error:", e)
    return jsonify({"ok": True})

@app.route("/api/assets/<a_id>/checkin", methods=["POST"])
@auth_required(module="assets", level="write")
def checkin_asset(a_id):
    c = conn(); cur = c.cursor()
    cur.execute("SELECT * FROM Assets WHERE _id=%s", [a_id]); a = cur.fetchone()
    if not a: c.close(); return jsonify({"error": "asset not found"}), 404
    old_status = a.get("Status")
    cur.execute("SELECT id FROM Checkouts WHERE asset_id=%s AND checkin_date IS NULL ORDER BY id DESC LIMIT 1", [a_id])
    co = cur.fetchone()
    if co:
        cur.execute("UPDATE Checkouts SET checkin_date=%s WHERE id=%s", (nowstr(), co["id"]))
    cur.execute("UPDATE Assets SET Status='Available', ReceivedBy='' WHERE _id=%s", [a_id])
    c.commit(); c.close()
    audit(session.get("user"), "CHECKIN", a_id, f"{a['Name']} returned")
    try:
        notify_asset_status_changed(a, old_status, "Available")
    except Exception as e:
        print("asset status-change notify error:", e)
    return jsonify({"ok": True})

# ---------- ITAM: maintenance ----------
@app.route("/api/assets/<a_id>/maintenance", methods=["GET", "POST", "DELETE"])
@auth_required(module="assets", level="write")
def maintenance(a_id):
    c = conn(); cur = c.cursor()
    if request.method == "GET":
        cur.execute("SELECT * FROM Maintenance WHERE asset_id=%s ORDER BY date DESC", [a_id])
        rows = cur.fetchall(); c.close()
        return jsonify([{k: r[k] for k in r} for r in rows])
    if request.method == "POST":
        d = request.get_json(force=True)
        cur.execute("INSERT INTO Maintenance (asset_id, date, mtype, cost, note, by_user) VALUES (%s,%s,%s,%s,%s,%s)",
                    (a_id, (d.get("date") or nowstr()), d.get("mtype", "Repair"),
                     float(d.get("cost") or 0), (d.get("note") or "").strip(), session.get("user")))
        # logging a maintenance record puts the asset under maintenance
        cur.execute("SELECT * FROM Assets WHERE _id=%s AND is_deleted=0", [a_id])
        arow = cur.fetchone()
        status_changed = False
        old_status = arow["Status"] if arow else None
        if arow and arow["Status"] != "Under-Maintenance":
            cur.execute("UPDATE Assets SET Status=%s WHERE _id=%s", ["Under-Maintenance", a_id])
            cur.execute("INSERT INTO History (asset_id, ts, user, field, old_val, new_val) VALUES (%s, NOW(), %s, %s, %s, %s)",
                        (a_id, session.get("user", "?"), "Status", arow["Status"], "Under-Maintenance"))
            status_changed = True
        c.commit(); c.close()
        audit(session.get("user"), "MAINTENANCE", a_id, f"{(d.get('mtype') or 'Repair')} cost {d.get('cost') or 0}")
        if status_changed and arow:
            try:
                notify_asset_status_changed(arow, old_status, "Under-Maintenance")
            except Exception as e:
                print("asset status-change notify error:", e)
        return jsonify({"ok": True})
    if request.method == "DELETE":
        mid = request.args.get("id")
        cur.execute("DELETE FROM Maintenance WHERE id=%s AND asset_id=%s", [mid, a_id]); c.commit(); c.close()
        return jsonify({"ok": True})

# ---------- audit log ----------
@app.route("/api/audit")
@feature_required("tools.audit")
def audit_log():
    c = conn(); cur = c.cursor()
    cur.execute("SELECT * FROM AuditLog ORDER BY ts DESC LIMIT 100"); rows = cur.fetchall(); c.close()
    return jsonify([{k: r[k] for k in r} for r in rows])

@app.route("/api/audit", methods=["DELETE"])
@auth_required([ROLE_ADMIN])
def clear_audit_log():
    c = conn(); cur = c.cursor()
    cur.execute("SELECT COUNT(*) AS n FROM AuditLog"); n = cur.fetchone()["n"]
    cur.execute("DELETE FROM AuditLog")
    c.commit(); c.close()
    audit(session.get("user"), "AUDIT_LOG_CLEARED", "", f"{n} entr{'y' if n==1 else 'ies'} removed")
    return jsonify({"ok": True, "deleted": n})

# ---------- dashboard stats ----------
@app.route("/api/dashboard")
@auth_required()
def dashboard():
    c = conn(); cur = c.cursor()
    cur.execute("SELECT _id, Status, PurchaseDate, WarrantyMonths, Type, Location FROM Assets WHERE is_deleted=0"); rows = cur.fetchall()
    today = datetime.now().date()
    total = len(rows)
    checked_out = sum(1 for r in rows if r["Status"] == "Checked-Out")
    maint = sum(1 for r in rows if r["Status"] == "Under-Maintenance")
    due_soon = 0; warranty_exp = 0
    for r in rows:
        try:
            pd = datetime.strptime(r["PurchaseDate"], "%Y-%m-%d").date()
            wm = int(r["WarrantyMonths"] or 12)
            end = pd + timedelta(days=wm * 30)
            if 0 <= (end - today).days <= 30: warranty_exp += 1
        except Exception: pass
    # checkouts due soon
    cur.execute("SELECT expected_checkin FROM Checkouts WHERE checkin_date IS NULL AND expected_checkin<>'' ")
    for r in cur.fetchall():
        try:
            ed = datetime.strptime(r["expected_checkin"], "%Y-%m-%d").date()
            if 0 <= (ed - today).days <= 7: due_soon += 1
        except Exception: pass
    # breakdowns for widgets
    by_status = {}
    by_type = {}
    by_location = {}
    for r in rows:
        by_status[r["Status"]] = by_status.get(r["Status"], 0) + 1
        by_type[r["Type"] or "Unspecified"] = by_type.get(r["Type"] or "Unspecified", 0) + 1
        by_location[r["Location"] or "Unspecified"] = by_location.get(r["Location"] or "Unspecified", 0) + 1
    # contracts: total / by type / expiring soon (for the dashboard "CONTRACTS" widgets)
    cur.execute("SELECT id, name, vendor, type, end_date, cost FROM Contracts WHERE is_deleted=0 ORDER BY end_date")
    crows = cur.fetchall()
    contracts_total = len(crows)
    contracts_by_type = {}
    contracts_expiring_soon = 0
    expiring_contracts = []
    for r in crows:
        t = r["type"] or "Other"
        contracts_by_type[t] = contracts_by_type.get(t, 0) + 1
        try:
            ed = datetime.strptime(r["end_date"], "%Y-%m-%d").date()
            days_left = (ed - today).days
            if 0 <= days_left <= 30:
                contracts_expiring_soon += 1
                expiring_contracts.append({"id": r["id"], "name": r["name"], "vendor": r["vendor"],
                                            "type": t, "end_date": r["end_date"], "days_left": days_left})
        except Exception: pass
    expiring_contracts.sort(key=lambda x: x["days_left"])
    c.close()
    return jsonify({"total": total, "checked_out": checked_out, "maintenance": maint,
                    "due_soon": due_soon, "warranty_expiring": warranty_exp,
                    "by_status": by_status, "by_type": by_type, "by_location": by_location,
                    "contracts_total": contracts_total, "contracts_by_type": contracts_by_type,
                    "contracts_expiring_soon": contracts_expiring_soon, "expiring_contracts": expiring_contracts[:12]})

# ---------- QR label ----------
@app.route("/api/assets/<a_id>/qr")
@auth_required(module="assets", level="read")
def asset_qr(a_id):
    c = conn(); cur = c.cursor()
    cur.execute("SELECT _id, " + ", ".join(f"`{col}`" for col in COLUMNS) + ", InvoiceFile FROM Assets WHERE _id=%s", [a_id])
    a = cur.fetchone(); c.close()
    if not a: return jsonify({"error": "not found"}), 404
    asset = row_to_dict(a)
    return jsonify({"asset": asset, "url": f"{lan_base_url()}asset/{a_id}"})

@app.route("/label/<a_id>")
def label_page(a_id):
    # Build a LAN-reachable base URL so QR codes scan from any device on the network
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80)); lan_ip = s.getsockname()[0]; s.close()
    except Exception:
        lan_ip = "127.0.0.1"
    base = f"http://{lan_ip}:5000/"
    c = conn(); cur = c.cursor()
    cur.execute("SELECT _id, " + ", ".join(f"`{col}`" for col in COLUMNS) + ", InvoiceFile FROM Assets WHERE _id=%s", [a_id])
    a = cur.fetchone(); c.close()
    if not a: return "Asset not found", 404
    asset = row_to_dict(a)
    # QR / label config from Settings
    try:
        sc = conn(); scur = sc.cursor()
        scur.execute("SELECT qr_size, qr_fields, label_size, label_logo, app_name, logo_text FROM Settings WHERE id=1")
        srow = scur.fetchone(); sc.close()
        qr_size = int(srow.get("qr_size") or 160) if srow else 160
        label_size = (srow.get("label_size") or "50.8x50.8")
        show_logo = bool(srow.get("label_logo", 1)) if srow else True
        app_name = (srow.get("app_name") or "IT-Vault") if srow else "IT-Vault"
        logo_text = (srow.get("logo_text") or app_name) if srow else app_name
    except Exception:
        qr_size, label_size, show_logo, app_name, logo_text = 160, "50.8x50.8", True, "IT-Vault", "IT-Vault"
    # parse label physical size "WxH" mm (default 50.8x50.8)
    try:
        lw, lh = label_size.lower().split("x")
        lw_mm, lh_mm = float(lw), float(lh)
    except Exception:
        lw_mm, lh_mm = 50.8, 50.8
    # Short/rectangular labels (e.g. 5.08x2.54cm) don't have room for a full-size
    # header + stacked two-line fields — switch to a compact single-line layout so
    # the label actually renders at (and fits) the physical size chosen, instead of
    # silently growing taller than requested.
    compact = lh_mm < 35.0
    pad_mm = 1.5 if compact else 2.5
    head_mm = 0.0 if compact else 5.5
    name_mm = 2.6 if compact else 4.0
    gap_mm = 0.5 if compact else 1.0
    reserved_mm = pad_mm * 2 + head_mm + name_mm + gap_mm * (1 if compact else 2)
    avail_h_mm = max(6.0, lh_mm - reserved_mm)
    # QR must fit both the label width and whatever vertical room is left
    qr_mm = max(8.0, min(float(qr_size)/3.78, lw_mm - 7.0, avail_h_mm))
    qr_px = int(qr_mm * 3.78)
    # embed logo as base64 if present (no extra request, prints reliably)
    logo_uri = _logo_data_uri()
    rows_html = ""
    field_defs = {
        "Name": ("Asset", asset.get("Name")),
        "AssetID": ("Asset ID", asset["_id"][:12]),
        "Type": ("Category", asset.get("Type")),
        "Serial": ("Serial", asset.get("Serial")),
        "Status": ("Status", asset.get("Status")),
        "Location": ("Location", asset.get("Location")),
        "ReceivedBy": ("Signed By", asset.get("ReceivedBy")),
        "ReceiverDate": ("Signed Date", asset.get("NotesReceived")),
        "EmployeeID": ("Employee ID", asset.get("EmployeeID")),
        "Department": ("Department", asset.get("Department")),
        "Warranty": ("Warranty", str(asset.get("WarrantyMonths") or 12) + " mo"),
        "PurchaseDate": ("Purchase", asset.get("PurchaseDate")),
        "Note": ("Note", asset.get("Note")),
    }
    chosen = [f.strip() for f in (srow.get("qr_fields") or "Name,AssetID,Type,Serial,Status,Location").split(",") if f.strip()] if srow else ["Name","AssetID","Type","Serial","Status","Location"]
    # Always ensure Category + Asset ID appear (per asset-tag requirement) if not already chosen
    for forced in ["Type", "AssetID"]:
        if forced not in chosen:
            chosen.insert(1 if forced == "Type" else len(chosen), forced)
    for key in chosen:
        if key == "Name" or key not in field_defs: continue
        lbl, val = field_defs[key]
        if val is None or val == "": continue
        if compact:
            rows_html += f"<div class=kv><b>{lbl}:</b> {val}</div>"
        else:
            rows_html += f"<div class=k>{lbl}</div><div class=v>{val}</div>"
    logo_html = ""
    if show_logo and logo_uri:
        logo_html = f'<img class=logo src="{logo_uri}" alt="">'
    head_block = (f'<div class=name>{logo_html}{asset["Name"]}</div>' if compact
                  else f'<div class=head>{logo_html}<span class=brand>{app_name}</span></div><div class=name>{asset["Name"]}</div>')
    return f"""<!doctype html><html><head><meta charset=utf-8><title>Label {asset['Name']}</title>
<style>
 body{{font-family:'Segoe UI',Arial,sans-serif;margin:0;padding:0;background:#fff}}
 .sheet{{display:flex;justify-content:center;padding:20px}}
 .box{{border:1px solid #222;padding:{pad_mm}mm;border-radius:3px;width:{lw_mm}mm;height:{lh_mm}mm;box-sizing:border-box;display:flex;flex-direction:column;gap:{gap_mm}mm;overflow:hidden}}
 .head{{display:flex;align-items:center;gap:1.5mm;border-bottom:0.4mm solid #222;padding-bottom:1mm;margin-bottom:0.5mm}}
 .logo{{height:{'3mm' if compact else '5mm'};width:auto;max-width:{'10mm' if compact else '18mm'};object-fit:contain}}
 .name .logo{{margin-right:1mm;vertical-align:middle}}
 .brand{{font-weight:800;font-size:3mm;letter-spacing:0.3mm;text-transform:uppercase}}
 .cat{{font-size:2.4mm;color:#333;margin:0.3mm 0}}
 .top{{display:flex;justify-content:space-between;align-items:flex-start;gap:2mm;flex:1;min-height:0;overflow:hidden}}
 .meta{{flex:1;min-width:0;overflow:hidden}}
 .name{{font-weight:700;font-size:{name_mm}mm;line-height:1.1;white-space:{'nowrap' if compact else 'normal'};overflow:hidden;text-overflow:ellipsis;word-break:break-word}}
 .k{{color:#555;font-size:1.9mm;line-height:1.05}}
 .v{{font-size:2.4mm;line-height:1.1;margin-bottom:0.5mm;word-break:break-word}}
 .kv{{font-size:1.7mm;line-height:1.3;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#333}}
 .kv b{{color:#555;font-weight:600}}
 .aid{{font-family:monospace;font-size:2.6mm;font-weight:700}}
 .qr{{flex:0 0 auto;width:{qr_px}px;height:{qr_px}px}}
 @media print{{
   @page{{size:{lw_mm}mm {lh_mm}mm;margin:0}}
   body{{background:#fff}}
   .sheet{{padding:0;display:block}}
   .box{{width:{lw_mm}mm;height:{lh_mm}mm;border:1px solid #222}}
   .no-print{{display:none}}
 }}
</style></head><body>
<script src="https://cdn.jsdelivr.net/npm/qrcodejs@1.0.0/qrcode.min.js"></script>
<div class=sheet><div class=box>
 {head_block}
 <div class=top>
   <div class=meta>
     {rows_html}
   </div>
   <div id=qr class=qr></div>
 </div>
</div></div>
<div class="no-print" style="text-align:center;margin-top:10px"><button onclick="window.print()">🖨 PRINT LABEL</button></div>
<script>new QRCode(document.getElementById('qr'), {{text:'{base}asset/{asset['_id']}',width:{qr_px},height:{qr_px},correctLevel:QRCode.CorrectLevel.M}});</script>
</body></html>"""

@app.route("/labels")
def labels_page():
    # Batch version of /label/<id> -- prints one QR label per selected asset on a
    # single page (?ids=a,b,c), in the order the caller passed them.
    ids = [i.strip() for i in (request.args.get("ids") or "").split(",") if i.strip()]
    if not ids:
        return "No assets specified", 400
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80)); lan_ip = s.getsockname()[0]; s.close()
    except Exception:
        lan_ip = "127.0.0.1"
    base = f"http://{lan_ip}:5000/"
    c = conn(); cur = c.cursor()
    placeholders = ",".join(["%s"] * len(ids))
    cur.execute("SELECT _id, " + ", ".join(f"`{col}`" for col in COLUMNS) + f", InvoiceFile FROM Assets WHERE _id IN ({placeholders})", ids)
    rows = cur.fetchall(); c.close()
    if not rows:
        return "No matching assets found", 404
    by_id = {r["_id"]: row_to_dict(r) for r in rows}
    ordered = [by_id[i] for i in ids if i in by_id]
    # QR / label config from Settings (shared by every label on this sheet)
    try:
        sc = conn(); scur = sc.cursor()
        scur.execute("SELECT qr_size, qr_fields, label_size, label_logo, app_name, logo_text FROM Settings WHERE id=1")
        srow = scur.fetchone(); sc.close()
        qr_size = int(srow.get("qr_size") or 160) if srow else 160
        label_size = (srow.get("label_size") or "50.8x50.8")
        show_logo = bool(srow.get("label_logo", 1)) if srow else True
        app_name = (srow.get("app_name") or "IT-Vault") if srow else "IT-Vault"
    except Exception:
        qr_size, label_size, show_logo, app_name = 160, "50.8x50.8", True, "IT-Vault"
    try:
        lw, lh = label_size.lower().split("x")
        lw_mm, lh_mm = float(lw), float(lh)
    except Exception:
        lw_mm, lh_mm = 50.8, 50.8
    compact = lh_mm < 35.0
    pad_mm = 1.5 if compact else 2.5
    head_mm = 0.0 if compact else 5.5
    name_mm = 2.6 if compact else 4.0
    gap_mm = 0.5 if compact else 1.0
    reserved_mm = pad_mm * 2 + head_mm + name_mm + gap_mm * (1 if compact else 2)
    avail_h_mm = max(6.0, lh_mm - reserved_mm)
    qr_mm = max(8.0, min(float(qr_size)/3.78, lw_mm - 7.0, avail_h_mm))
    qr_px = int(qr_mm * 3.78)
    logo_uri = _logo_data_uri()
    chosen = [f.strip() for f in (srow.get("qr_fields") or "Name,AssetID,Type,Serial,Status,Location").split(",") if f.strip()] if srow else ["Name","AssetID","Type","Serial","Status","Location"]
    for forced in ["Type", "AssetID"]:
        if forced not in chosen:
            chosen.insert(1 if forced == "Type" else len(chosen), forced)
    logo_html = f'<img class=logo src="{logo_uri}" alt="">' if (show_logo and logo_uri) else ""
    boxes_html = ""
    scripts = ""
    for idx, asset in enumerate(ordered):
        field_defs = {
            "Name": ("Asset", asset.get("Name")),
            "AssetID": ("Asset ID", asset["_id"][:12]),
            "Type": ("Category", asset.get("Type")),
            "Serial": ("Serial", asset.get("Serial")),
            "Status": ("Status", asset.get("Status")),
            "Location": ("Location", asset.get("Location")),
            "ReceivedBy": ("Signed By", asset.get("ReceivedBy")),
            "ReceiverDate": ("Signed Date", asset.get("NotesReceived")),
            "EmployeeID": ("Employee ID", asset.get("EmployeeID")),
            "Department": ("Department", asset.get("Department")),
            "Warranty": ("Warranty", str(asset.get("WarrantyMonths") or 12) + " mo"),
            "PurchaseDate": ("Purchase", asset.get("PurchaseDate")),
            "Note": ("Note", asset.get("Note")),
        }
        rows_html = ""
        for key in chosen:
            if key == "Name" or key not in field_defs: continue
            lbl, val = field_defs[key]
            if val is None or val == "": continue
            if compact:
                rows_html += f"<div class=kv><b>{lbl}:</b> {val}</div>"
            else:
                rows_html += f"<div class=k>{lbl}</div><div class=v>{val}</div>"
        head_block = (f'<div class=name>{logo_html}{asset["Name"]}</div>' if compact
                      else f'<div class=head>{logo_html}<span class=brand>{app_name}</span></div><div class=name>{asset["Name"]}</div>')
        qr_id = f"qr{idx}"
        boxes_html += f"""<div class=box>
 {head_block}
 <div class=top>
   <div class=meta>{rows_html}</div>
   <div id={qr_id} class=qr></div>
 </div>
</div>"""
        scripts += f"new QRCode(document.getElementById('{qr_id}'), {{text:'{base}asset/{asset['_id']}',width:{qr_px},height:{qr_px},correctLevel:QRCode.CorrectLevel.M}});"
    return f"""<!doctype html><html><head><meta charset=utf-8><title>Print {len(ordered)} Labels</title>
<style>
 body{{font-family:'Segoe UI',Arial,sans-serif;margin:0;padding:0;background:#fff}}
 .sheet{{display:flex;flex-wrap:wrap;gap:3mm;padding:20px}}
 .box{{border:1px solid #222;padding:{pad_mm}mm;border-radius:3px;width:{lw_mm}mm;height:{lh_mm}mm;box-sizing:border-box;display:flex;flex-direction:column;gap:{gap_mm}mm;overflow:hidden}}
 .head{{display:flex;align-items:center;gap:1.5mm;border-bottom:0.4mm solid #222;padding-bottom:1mm;margin-bottom:0.5mm}}
 .logo{{height:{'3mm' if compact else '5mm'};width:auto;max-width:{'10mm' if compact else '18mm'};object-fit:contain}}
 .name .logo{{margin-right:1mm;vertical-align:middle}}
 .brand{{font-weight:800;font-size:3mm;letter-spacing:0.3mm;text-transform:uppercase}}
 .top{{display:flex;justify-content:space-between;align-items:flex-start;gap:2mm;flex:1;min-height:0;overflow:hidden}}
 .meta{{flex:1;min-width:0;overflow:hidden}}
 .name{{font-weight:700;font-size:{name_mm}mm;line-height:1.1;white-space:{'nowrap' if compact else 'normal'};overflow:hidden;text-overflow:ellipsis;word-break:break-word}}
 .k{{color:#555;font-size:1.9mm;line-height:1.05}}
 .v{{font-size:2.4mm;line-height:1.1;margin-bottom:0.5mm;word-break:break-word}}
 .kv{{font-size:1.7mm;line-height:1.3;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#333}}
 .kv b{{color:#555;font-weight:600}}
 .qr{{flex:0 0 auto;width:{qr_px}px;height:{qr_px}px}}
 @media print{{
   @page{{size:{lw_mm}mm {lh_mm}mm;margin:0}}
   body{{background:#fff}}
   .sheet{{padding:0;gap:0}}
   .box{{border:1px solid #222;page-break-after:always}}
   .no-print{{display:none}}
 }}
</style></head><body>
<script src="https://cdn.jsdelivr.net/npm/qrcodejs@1.0.0/qrcode.min.js"></script>
<div class="no-print" style="text-align:center;margin:10px"><button onclick="window.print()">🖨 PRINT {len(ordered)} LABELS</button></div>
<div class=sheet>{boxes_html}</div>
<script>{scripts}</script>
</body></html>"""

@app.route("/asset/<a_id>")
def asset_public(a_id):
    # Public asset detail page (opened by scanning the QR from any device on the LAN)
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80)); lan_ip = s.getsockname()[0]; s.close()
    except Exception:
        lan_ip = "127.0.0.1"
    base = f"http://{lan_ip}:5000/"
    c = conn(); cur = c.cursor()
    cur.execute("SELECT _id, " + ", ".join(f"`{col}`" for col in COLUMNS) + ", InvoiceFile, SignatureData FROM Assets WHERE _id=%s", [a_id])
    a = cur.fetchone()
    if not a:
        c.close(); return "Asset not found", 404
    asset = row_to_dict(a)
    # assigned employee (from Employees by EmployeeID)
    emp_name = asset.get("EmployeeName") or ""
    if not emp_name and asset.get("EmployeeID"):
        try:
            ec = conn(); ecur = ec.cursor()
            ecur.execute("SELECT EmployeeName, Department, Designation, Email FROM Employees WHERE EmployeeID=%s", (asset["EmployeeID"],))
            er = ecur.fetchone(); ec.close()
            if er:
                emp_name = er.get("EmployeeName") or ""
                asset["Department"] = asset.get("Department") or er.get("Department") or ""
                asset["Designation"] = asset.get("Designation") or er.get("Designation") or ""
                asset["Email"] = asset.get("Email") or er.get("Email") or ""
        except Exception:
            pass
    # org branding + contact
    try:
        sc = conn(); scur = sc.cursor()
        scur.execute("SELECT app_name, logo_text, company_phone, company_address FROM Settings WHERE id=1")
        srow = scur.fetchone(); sc.close()
        app_name = (srow.get("app_name") or "IT-Vault") if srow else "IT-Vault"
        logo_text = (srow.get("logo_text") or app_name) if srow else app_name
        company_phone = (srow.get("company_phone") or "") if srow else ""
        company_address = (srow.get("company_address") or "") if srow else ""
    except Exception:
        app_name, logo_text, company_phone, company_address = "IT-Vault", "IT-Vault", "", ""
    # who actually processed this asset (the staff/admin account, as opposed to
    # ReceivedBy which is the person it was signed out to)
    processed_by = ""
    try:
        pc = conn(); pcur = pc.cursor()
        pcur.execute("SELECT actor FROM AuditLog WHERE asset_id=%s AND action IN ('CHECKOUT','ACKNOWLEDGE') ORDER BY id DESC LIMIT 1", [a_id])
        prow = pcur.fetchone(); pc.close()
        processed_by = (prow.get("actor") or "") if prow else ""
    except Exception:
        processed_by = ""
    # logo as base64
    logo_uri = _logo_data_uri()
    c.close()
    rows = [("Asset Name", asset.get("Name")), ("Asset ID", asset.get("AssetTag") or asset["_id"][:12]),
            ("Category", asset.get("Type")), ("Serial", asset.get("Serial")),
            ("Status", asset.get("Status")), ("Location", asset.get("Location")),
            ("Assigned To", emp_name or "—"), ("Department", asset.get("Department") or "—"),
            ("Designation", asset.get("Designation") or "—"), ("Email", asset.get("Email") or "—"),
            ("Signed By", asset.get("ReceivedBy") or "—"), ("Signed Date", asset.get("NotesReceived") or "—"),
            ("Given By (Staff)", processed_by or "—"),
            ("Warranty", str(asset.get("WarrantyMonths") or 12) + " mo"), ("Purchase", asset.get("PurchaseDate") or "—"),
            ("Note", asset.get("Note") or "—")]
    rows_html = "".join(f"<tr><td class='k'>{k}</td><td class='v'>{('' if v is None else v)}</td></tr>" for k,v in rows)
    logo_html = f'<img class=logo src="{logo_uri}" alt="">' if logo_uri else ""
    contact_bits = [c for c in [company_phone, company_address] if c]
    contact_html = " &nbsp;·&nbsp; ".join(contact_bits) if contact_bits else "—"
    return f"""<!doctype html><html lang="en"><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Asset {asset['Name']}</title>
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;900&family=Rajdhani:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/style.css">
<style>
*{{box-sizing:border-box}}
html{{overflow-y:auto}}
body{{font-family:'Rajdhani',sans-serif;margin:0;padding:28px 16px;padding-top:max(28px,env(safe-area-inset-top));padding-bottom:max(28px,env(safe-area-inset-bottom));min-height:100vh;min-height:100dvh;height:auto;background:var(--bg);color:var(--txt);overflow-y:auto!important;overflow-x:hidden;-webkit-overflow-scrolling:touch}}
.wrap{{max-width:560px;margin:0 auto}}
.card{{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:22px;box-shadow:0 10px 40px rgba(0,0,0,.35)}}
.head{{display:flex;align-items:center;gap:10px;border-bottom:1px solid var(--line);padding-bottom:12px;margin-bottom:14px}}
.logo{{height:32px;width:auto;max-width:120px;object-fit:contain}}
.brand{{font-family:'Orbitron';font-weight:800;font-size:16px;letter-spacing:.5px;background:linear-gradient(90deg,var(--accent),var(--accent2));-webkit-background-clip:text;background-clip:text;color:transparent;text-transform:uppercase}}
.assetid-badge{{font-family:'Share Tech Mono',var(--mono);font-size:14px;font-weight:700;letter-spacing:1px;color:var(--accent);background:var(--accent-soft);border:1px solid var(--accent);border-radius:999px;padding:5px 14px;display:inline-block;margin-bottom:10px}}
.title{{font-size:22px;font-weight:700;margin:0 0 14px}}
table{{width:100%;border-collapse:collapse}}
td{{padding:8px 6px;border-bottom:1px solid var(--line);vertical-align:top}}
tr:last-child td{{border-bottom:none}}
.k{{color:var(--muted);font-size:12px;width:42%;font-weight:600;text-transform:uppercase;letter-spacing:.3px}}
.v{{font-size:14px;font-weight:600;word-break:break-word}}
.contact{{margin-top:16px;padding:12px 14px;background:var(--surface2);border:1px solid var(--line);border-radius:var(--radius);font-size:14px}}
.contact b{{color:var(--accent)}}
.foot{{text-align:center;color:var(--muted);font-size:12px;margin-top:18px}}
a.btn{{display:inline-block;margin-top:14px;padding:10px 16px;background:var(--accent);color:#fff;border-radius:var(--radius);text-decoration:none;font-weight:700;font-size:13px}}
.sig-block{{margin-top:16px;padding:12px 14px;background:var(--surface2);border:1px solid var(--line);border-radius:var(--radius)}}
.sig-block b{{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.3px;display:block;margin-bottom:8px}}
.sig-block img{{max-width:220px;max-height:110px;background:#fff;border-radius:6px;padding:6px}}
@media(max-width:480px){{ body{{padding:16px 10px}} .card{{padding:16px}} }}
</style></head><body><div class=wrap><div class=card>
 <div class=head>{logo_html}<span class=brand>{app_name}</span></div>
 <div class=assetid-badge>{asset.get("AssetTag") or asset["_id"][:12]}</div>
 <div class=title>{asset['Name']}</div>
 <table>{rows_html}</table>
 {f'<div class=sig-block><b>Signature</b><img src="{asset.get("SignatureData")}"></div>' if asset.get("SignatureData") else ''}
 <div class=contact>📞 Organization Contact: <b>{contact_html}</b></div>
 <a class=btn href="{base}label/{asset['_id']}">🖨 Open Printable Tag</a>
 <div class=foot>Scanned from {app_name} • {base}</div>
</div></div></body></html>"""

# ---------- invoice attachment ----------
ALLOWED_EXT = {"pdf", "png", "jpg", "jpeg", "gif", "webp", "bmp", "tif", "tiff"}
import mimetypes as _mtype

@app.route("/api/assets/<a_id>/invoice", methods=["POST"])
@auth_required(module="assets", level="write")
def upload_invoice(a_id):
    if "file" not in request.files:
        return jsonify({"error": "no file"}), 400
    f = request.files["file"]
    if not f or f.filename == "":
        return jsonify({"error": "empty filename"}), 400
    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    if ext not in ALLOWED_EXT:
        return jsonify({"error": "only PDF/image allowed"}), 400
    c = conn(); cur = c.cursor()
    cur.execute("SELECT _id, InvoiceFile FROM Assets WHERE _id=%s", [a_id]); a = cur.fetchone()
    if not a: c.close(); return jsonify({"error": "asset not found"}), 404
    # remove old invoice file if present
    old = a.get("InvoiceFile")
    if old:
        try: os.remove(os.path.join(INVOICE_DIR, old))
        except Exception: pass
    stored = f"{a_id}.{ext}"
    f.save(os.path.join(INVOICE_DIR, stored))
    cur.execute("UPDATE Assets SET InvoiceFile=%s WHERE _id=%s", (stored, a_id))
    c.commit(); c.close()
    audit(session.get("user"), "INVOICE", a_id, f"uploaded {f.filename}")
    return jsonify({"ok": True, "file": stored})

@app.route("/api/assets/<a_id>/invoice", methods=["DELETE"])
@auth_required(module="assets", level="write")
def delete_invoice(a_id):
    c = conn(); cur = c.cursor()
    cur.execute("SELECT InvoiceFile FROM Assets WHERE _id=%s", [a_id]); a = cur.fetchone()
    if not a: c.close(); return jsonify({"error": "asset not found"}), 404
    fn = a.get("InvoiceFile")
    if fn:
        try: os.remove(os.path.join(INVOICE_DIR, fn))
        except Exception: pass
        cur.execute("UPDATE Assets SET InvoiceFile=NULL WHERE _id=%s", [a_id])
        c.commit()
    c.close()
    return jsonify({"ok": True})

@app.route("/invoice/<path:fn>")
@auth_required()
def serve_invoice(fn):
    # prevent path traversal
    fn = os.path.basename(fn)
    full = os.path.join(INVOICE_DIR, fn)
    if not os.path.exists(full): return "not found", 404
    return send_from_directory(INVOICE_DIR, fn, mimetype=_mtype.guess_type(fn)[0] or "application/octet-stream")

# ---------- signature link ----------
import base64, hmac, hashlib, json as _json
def _sign_token(data, exp_hours=168):
    payload = _json.dumps({"a":data,"exp":int(time.time())+exp_hours*3600}, separators=(',',':'))
    b64 = base64.urlsafe_b64encode(payload.encode()).decode().rstrip('=')
    sig = hmac.new(SECRET.encode(), b64.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{b64}.{sig}"

def _verify_token(tk):
    try:
        if not tk or '.' not in tk: return None
        b64, sig = tk.rsplit('.', 1)
        expected = hmac.new(SECRET.encode(), b64.encode(), hashlib.sha256).hexdigest()[:16]
        if not hmac.compare_digest(sig, expected): return None
        payload = base64.urlsafe_b64decode(b64 + '==').decode()
        obj = _json.loads(payload)
        if obj.get('exp',0) < time.time(): return None
        return obj.get('a')
    except Exception:
        return None

@app.route("/api/assets/<a_id>/sign/link")
@auth_required(module="assets", level="write")
def get_sign_link(a_id):
    c = conn(); cur = c.cursor()
    cur.execute("SELECT _id, Name FROM Assets WHERE _id=%s", [a_id]); a = cur.fetchone()
    if not a: c.close(); return jsonify({"error": "asset not found"}), 404
    tk = _sign_token({"asset_id":a_id, "name":a["Name"]}, exp_hours=7)
    c.close()
    return jsonify({"ok": True, "token": tk, "url": f"{request.host_url}sign?token={quote(tk)}"})

SIGNATURE_HTML = """<!doctype html><html lang="en"><head><meta charset=utf-8><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,viewport-fit=cover">
<title>IT-Vault // Asset Acknowledgement</title>
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;900&family=Share+Tech+Mono&family=Rajdhani:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/style.css">
<style>
*{box-sizing:border-box}
html{overflow-y:auto}
body{font-family:'Rajdhani',sans-serif;margin:0;padding:28px 16px;padding-top:max(28px,env(safe-area-inset-top));padding-bottom:max(28px,env(safe-area-inset-bottom));min-height:100vh;min-height:100dvh;height:auto;background:var(--bg);color:var(--txt);transition:background .25s,color .25s;overflow-y:auto!important;overflow-x:hidden;-webkit-overflow-scrolling:touch}
.sign-card{max-width:620px;margin:0 auto;background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:26px 26px 22px;box-shadow:0 10px 40px rgba(0,0,0,.35)}
.brand{font-family:'Orbitron';font-weight:900;font-size:26px;text-align:center;background:linear-gradient(90deg,var(--accent),var(--accent2));-webkit-background-clip:text;background-clip:text;color:transparent;margin:0 0 2px}
.sub{text-align:center;color:var(--muted);font-size:12px;letter-spacing:3px;margin-bottom:18px}
.assetid-badge{text-align:center;font-family:'Share Tech Mono',var(--mono);font-size:15px;font-weight:700;letter-spacing:1px;color:var(--accent);background:var(--accent-soft);border:1px solid var(--accent);border-radius:999px;padding:6px 16px;margin:0 auto 18px;display:table}
.assetid-badge:empty{display:none}
.asset-table{width:100%;table-layout:fixed;border-collapse:collapse;margin:10px 0 18px;background:var(--surface2);border:1px solid var(--line);border-radius:var(--radius);overflow:hidden}
.asset-table td{padding:9px 14px;border-bottom:1px solid var(--line);font-size:14px}
.asset-table tr:last-child td{border-bottom:none}
.asset-table td:first-child{color:var(--muted);width:150px;font-size:12px;font-weight:600;letter-spacing:.3px;text-transform:uppercase;vertical-align:top}
.asset-table td:last-child{color:var(--txt);font-weight:600;word-break:break-word;overflow-wrap:anywhere;white-space:pre-line}
.sig-label{color:var(--muted);font-size:13px;margin-bottom:6px;display:block}
#sigCanvas{width:100%;max-width:480px;height:160px;border-radius:var(--radius);background:var(--surface2);border:2px solid var(--line);cursor:crosshair;display:none;touch-action:none}
#sigPlaceholder{width:100%;max-width:480px;height:160px;display:flex;align-items:center;justify-content:center;color:var(--muted);font-size:14px;border:2px dashed var(--line);border-radius:var(--radius);background:var(--surface2);cursor:pointer}
#sigPlaceholder.hidden{display:none}
.btnrow{display:flex;gap:10px;flex-wrap:wrap;margin-top:8px}
.btnrow .btn{flex:1;min-width:140px;min-height:44px}
#result{margin-top:16px;font-size:14px;min-height:24px}
.ok{color:var(--grn)}.err{color:var(--red);white-space:pre-wrap}
.center{text-align:center;margin-top:40px;color:var(--muted)}
@media (max-width:480px){
  body{padding:16px 10px}
  .sign-card{padding:18px 16px 16px;border-radius:calc(var(--radius) - 2px)}
  .brand{font-size:22px}
  .asset-table{display:block}
  .asset-table tr{display:flex;flex-direction:column;padding:8px 12px}
  .asset-table td{display:block;padding:2px 0;border-bottom:none;width:auto!important}
  .asset-table td:first-child{padding-top:6px}
  .asset-table tr:not(:last-child){border-bottom:1px solid var(--line)}
  .btnrow .btn{min-width:100%}
}
</style></head><body>
<div class="sign-card">
  <div class="brand" id="brand">IT-Vault</div>
  <div class="sub" id="sub">// ASSET ACKNOWLEDGEMENT</div>
  <div class="assetid-badge" id="assetIdBadge"></div>
  <div id="assetCard"></div>
  <div class="field2"><label>Your Full Name</label><input id="signer" placeholder="Enter your full name"></div>
  <div class="sig-wrap">
    <span class="sig-label">Signature</span>
    <div id="sigPlaceholder">✏️ Click here to sign</div>
    <canvas id="sigCanvas"></canvas>
  </div>
  <div class="btnrow">
    <button class="btn ghost" id="clearSign" style="display:none">🗑 CLEAR</button>
    <button class="btn ghost" id="viewSign" style="display:none">🖼 VIEW SIGNATURE</button>
    <button class="btn" id="saveSign">✅ SUBMIT ACKNOWLEDGEMENT</button>
  </div>
  <div id="result"></div>
</div>
<script>
const token = new URLSearchParams(window.location.search).get('token');
if(!token){document.body.innerHTML='<div class=sign-card><h3>❌ No token</h3><p>Invalid or missing signature link.</p></div>';throw 0;}
const placeholder=document.getElementById('sigPlaceholder');
const canvas=document.getElementById('sigCanvas');
let ctx=null, isDrawing=false, hasSig=false;
function accentColor(){try{return getComputedStyle(document.documentElement).getPropertyValue('--accent').trim()||'#ff3b30';}catch(e){return '#ff3b30';}}
function initCanvas(){
  if(ctx) return;
  // Must run AFTER the canvas is actually visible -- offsetWidth/Height read
  // 0 on a display:none element, which used to lock the drawing buffer to the
  // 480x160 fallback regardless of the phone's real (narrower) screen width,
  // making touches land in the wrong spot on mobile. Also scales the buffer
  // by devicePixelRatio so the line doesn't look blurry on retina/high-DPI
  // phone screens.
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.offsetWidth||480, h = canvas.offsetHeight||160;
  canvas.width = Math.round(w*dpr); canvas.height = Math.round(h*dpr);
  ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  ctx.lineWidth = 2; ctx.lineCap='round'; ctx.lineJoin='round';
  ctx.strokeStyle = accentColor();
  // No fillRect here on purpose -- the canvas's own CSS background (dark,
  // matching the page) shows through while signing, but the drawing buffer
  // itself stays transparent, so the exported PNG (toDataURL) is just the
  // stroke with a transparent background. A baked-in dark fill here used to
  // ship as an opaque black box wherever the signature got embedded later
  // (the emailed PDF, the QR scan page), regardless of that page's own
  // background color.
}
function getPos(e){
  const rect=canvas.getBoundingClientRect();
  const x=(e.touches?e.touches[0].clientX:e.clientX)-rect.left;
  const y=(e.touches?e.touches[0].clientY:e.clientY)-rect.top;
  return {x,y};
}
function startDraw(e){
  if(!ctx) initCanvas();
  isDrawing=true; e.preventDefault&&e.preventDefault();
  const p=getPos(e); ctx.beginPath(); ctx.moveTo(p.x,p.y);
}
function draw(e){
  if(!isDrawing||!ctx) return;
  e.preventDefault();
  const p=getPos(e); ctx.lineTo(p.x,p.y); ctx.stroke(); hasSig=true; updateClearBtn();
}
function stopDraw(){ if(!isDrawing) return; isDrawing=false; ctx.beginPath(); updateClearBtn(); }
function showCanvas(){ placeholder.classList.add('hidden'); canvas.style.display='block'; initCanvas(); canvas.focus(); }
placeholder.addEventListener('click',()=>{showCanvas();});
canvas.addEventListener('mousedown',startDraw);
canvas.addEventListener('mousemove',draw);
canvas.addEventListener('mouseup',stopDraw);
canvas.addEventListener('mouseleave',stopDraw);
canvas.addEventListener('touchstart',startDraw,{passive:false});
canvas.addEventListener('touchmove',draw,{passive:false});
canvas.addEventListener('touchend',stopDraw,{passive:false});
function clearSig(){ if(!ctx) return; ctx.save(); ctx.setTransform(1,0,0,1,0,0); ctx.clearRect(0,0,canvas.width,canvas.height); ctx.restore(); hasSig=false; const c=document.getElementById('clearSign'); if(c)c.style.display='none'; }
function updateClearBtn(){ const c=document.getElementById('clearSign'); if(!c) return; c.style.display = hasSig?'block':'none'; }
function getSigData(){return canvas.toDataURL('image/png');}
function esc(s){const d=document.createElement('div');d.textContent=s||'';return d.innerHTML;}
async function load(){
  const r=await fetch('/api/assets/sign/verify?token='+encodeURIComponent(token));
  const j=await r.json();
  if(!j.ok){document.getElementById('assetCard').innerHTML='<p class=err>❌ '+j.error+'</p>';throw 0;}
  const a=j.asset;
  const receivedBy = a.ReceivedBy || a.received_by || '';
  const notesReceived = a.NotesReceived || a.notes_received || '';
  const viewBtn=document.getElementById('viewSign');
  if(viewBtn){ if(a.SignatureData){ viewBtn.style.display='block'; viewBtn.onclick=()=>{const w=window.open('','_blank');w.document.write('<img src="'+a.SignatureData+'" style="max-width:100%"/>');}; } else { viewBtn.style.display='none'; } }
  document.getElementById('assetIdBadge').textContent = a.AssetTag||a.asset_tag||'';
  document.getElementById('assetCard').innerHTML=
    '<table class=asset-table>'+
    '<tr><td>Asset ID</td><td>'+esc(a.AssetTag||a.asset_tag||'—')+'</td></tr>'+
    '<tr><td>Name</td><td>'+esc(a.Name)+'</td></tr>'+
    '<tr><td>Type</td><td>'+esc(a.Type)+'</td></tr>'+
    '<tr><td>Serial</td><td>'+esc(a.Serial)+'</td></tr>'+
    '<tr><td>Status</td><td>'+esc(a.Status)+'</td></tr>'+
    '<tr><td>Location</td><td>'+esc(a.Location)+'</td></tr>'+
    (a.Department?'<tr><td>Department</td><td>'+esc(a.Department)+'</td></tr>':'')+
    (a.Designation?'<tr><td>Designation</td><td>'+esc(a.Designation)+'</td></tr>':'')+
    '<tr><td>Notes</td><td>'+esc(a.Notes||'—')+'</td></tr>'+
    '<tr><td>Received By</td><td>'+esc(receivedBy||'Not yet received')+'</td></tr>'+
    '<tr><td>Received Details</td><td>'+esc(notesReceived||'Not yet received')+'</td></tr>'+
    '</table>';
}
document.getElementById('clearSign').addEventListener('click',()=>{clearSig();});
document.getElementById('viewSign').addEventListener('click',()=>{const sig=(document.querySelector('meta[data-sig]')||{}).content||''; if(!sig){alert('No signature');return;} const w=window.open('','_blank'); w.document.write('<img src="'+sig+'" style="max-width:100%"/>'); });
document.getElementById('saveSign').addEventListener('click',async()=>{
  const name=document.getElementById('signer').value.trim();
  const res=document.getElementById('result');
  if(!name){res.className='err';res.textContent='⚠ Please enter your name.';return;}
  if(!hasSig||!ctx||ctx.getImageData(0,0,canvas.width,canvas.height).data.filter(c=>c>0).length<100){ res.className='err';res.textContent='⚠ Please sign above.';return; }
  const data=getSigData();
  res.textContent='Submitting…';
  const r=await fetch('/api/assets/sign/approve',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token,name,data})});
  const j=await r.json();
  if(j.ok){res.className='ok';res.innerHTML=j.emailed?'✅ <b>Acknowledged</b> — thank you. A signed copy has been sent to your email.':'✅ <b>Acknowledged</b> — thank you. Your signature has been recorded.';document.querySelector('.btn').disabled=true;document.getElementById('signer').disabled=true;placeholder.classList.add('hidden');clearSig();const v=document.getElementById('viewSign');if(v){v.style.display='block';v.onclick=()=>{const w=window.open('','_blank');w.document.write('<img src="'+data+'" style="max-width:100%"/>');};}}
  else{res.className='err';res.textContent='❌ '+(j.error||'Failed');}
});
/* ---- branding + theme (same color math as the main app / login page, so
   this publicly-shared page always gets correct, readable colors instead of
   just a few vars copied straight through) ---- */
function hex6(v, fb){
  const s=String(v==null?'':v).trim();
  if(/^#[0-9a-fA-F]{6}$/.test(s)) return s.toLowerCase();
  if(/^#[0-9a-fA-F]{3}$/.test(s)) return ('#'+s[1]+s[1]+s[2]+s[2]+s[3]+s[3]).toLowerCase();
  return fb;
}
function hexRgb(h){ const s=hex6(h,'#000000'); return [parseInt(s.slice(1,3),16),parseInt(s.slice(3,5),16),parseInt(s.slice(5,7),16)]; }
function rgba(h,a){ const c=hexRgb(h); return 'rgba('+c[0]+','+c[1]+','+c[2]+','+a+')'; }
function shade(h,amt){ const c=hexRgb(h); const f=n=>{const v=Math.max(0,Math.min(255,Math.round(n+255*amt)));return v.toString(16).padStart(2,'0');}; return '#'+f(c[0])+f(c[1])+f(c[2]); }
function isLightHex(h){ const c=hexRgb(h); return (c[0]*0.299+c[1]*0.587+c[2]*0.114)>150; }
function onBg(bgHex){ return isLightHex(bgHex)?'#16202e':'#e6edf6'; }
function muteFor(bgHex,k){ const light=isLightHex(bgHex); if(light) return k==='muted'?'#5d6b82':'#8595ad'; return k==='muted'?'#8a98b0':'#5d6b82'; }
function contrastRatio(a,b){ const L=h=>{const [r,g,bl]=hexRgb(h).map(v=>{v/=255;return v<=0.03928?v/12.92:Math.pow((v+0.055)/1.055,2.4);});return 0.2126*r+0.7152*g+0.0722*bl;}; const la=L(a),lb=L(b); const hi=Math.max(la,lb),lo=Math.min(la,lb); return (hi+0.05)/(lo+0.05); }
function ensureAccentVisible(accent,surface){ if(contrastRatio(accent,surface)>=2.2) return accent; const a=hexRgb(accent),s=hexRgb(surface); const mix=a.map((v,i)=>Math.round(v*0.65+s[i]*0.35)); return '#'+mix.map(v=>v.toString(16).padStart(2,'0')).join(''); }
function applySignTheme(b){
  try{
    const bgType=b.bg_type==='gradient'?'gradient':'solid';
    const bgRaw=String(b.bg||'').trim();
    let bgA='#0a0d13', bgB='#121826';
    if(bgType==='gradient'){
      const found=bgRaw.match(/#[0-9a-fA-F]{3,6}/g)||[];
      bgA=hex6(found[0],'#0a0d13'); bgB=hex6(found[1],'#121826');
    }
    const baseHex=bgType==='gradient'?bgA:hex6(bgRaw,'#0a0d13');
    const bgValue=bgType==='gradient'?('linear-gradient(135deg, '+bgA+', '+bgB+')'):baseHex;
    const surface=hex6(b.comp_bg,'#121826');
    const light=isLightHex(baseHex);
    const surfaceLight=isLightHex(surface);
    const accent=ensureAccentVisible(hex6(b.accent,'#ff3b30'), surface);
    const accent2=ensureAccentVisible(hex6(b.accent2,'#c0392b'), surface);
    const radius=Math.max(0,Math.min(24,parseInt(b.radius,10)||12));
    const r=document.documentElement.style;
    r.setProperty('--bg', bgValue);
    r.setProperty('--bg1', light?shade(baseHex,-0.04):shade(baseHex,0.03));
    r.setProperty('--surface', surface);
    r.setProperty('--surface2', surfaceLight?shade(surface,-0.04):shade(surface,-0.02));
    r.setProperty('--line', surfaceLight?shade(surface,-0.14):shade(surface,0.10));
    r.setProperty('--line2', surfaceLight?shade(surface,-0.22):shade(surface,0.16));
    r.setProperty('--txt', onBg(baseHex));
    r.setProperty('--muted', muteFor(baseHex,'muted'));
    r.setProperty('--muted2', muteFor(baseHex,'muted2'));
    r.setProperty('--accent', accent);
    r.setProperty('--accent2', accent2);
    r.setProperty('--accent-soft', rgba(accent,0.14));
    r.setProperty('--radius', radius+'px');
    document.body.classList.toggle('light', light);
  }catch(e){}
}
(async()=>{ try{
  const b=await (await fetch('/api/branding')).json();
  const name=b.app_name||'IT-Vault';
  document.title=name+' // Asset Acknowledgement';
  const brand=document.getElementById('brand'); brand.textContent=name;
  document.getElementById('sub').textContent='// ASSET ACKNOWLEDGEMENT';
  applySignTheme(b);
}catch(e){} })();
load();
</script></body></html>"""

@app.route("/sign")
def sign_page():
    return SIGNATURE_HTML

@app.route("/api/assets/sign/verify")
def verify_sign():
    tk = request.args.get("token","");
    d = _verify_token(tk)
    if not d: return jsonify({"ok": False, "error": "invalid or expired token"}), 400
    c = conn(); cur = c.cursor()
    cur.execute("SELECT _id AS id, AssetTag, Name, Type, Serial, Status, Location, Notes, ReceivedBy, NotesReceived, SignatureData, EmployeeID FROM Assets WHERE _id=%s", [d["asset_id"]]); a = cur.fetchone()
    if not a: c.close(); return jsonify({"ok": False, "error": "asset not found"}), 404
    if a.get("EmployeeID"):
        cur.execute("SELECT Department, Designation FROM Employees WHERE EmployeeID=%s", [a["EmployeeID"]])
        er = cur.fetchone()
        if er:
            a["Department"] = er.get("Department") or ""
            a["Designation"] = er.get("Designation") or ""
    c.close()
    return jsonify({"ok": True, "asset": a})

def _build_signed_asset_pdf(asset, signer_name, sig_data_url):
    """One-page A4 PDF of the signed acknowledgement -- Asset ID front and
    center, full details, and the captured signature -- emailed to both the
    assigned user and the admin team the moment someone submits /sign."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER

    # A letterhead is a whole printed page, so it has to be a full-page
    # background behind the flowed content (drawn via onFirstPage/onLaterPages
    # below) -- NOT stacked as an inline flowable at the top of the story.
    # Stacking it inline was the earlier "not aligned" bug: at the story's
    # ~178mm content width, a full A4-shaped image renders ~252mm tall on its
    # own, swallowing almost the entire page before any real content starts.
    letterhead_path = LETTERHEAD_PATH
    used_letterhead = os.path.exists(letterhead_path) and os.path.getsize(letterhead_path) > 0

    buf = io.BytesIO()
    top_margin = 42 * mm if used_letterhead else 16 * mm
    bottom_margin = 30 * mm if used_letterhead else 16 * mm
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=top_margin, bottomMargin=bottom_margin,
                             leftMargin=16 * mm, rightMargin=16 * mm)
    styles = getSampleStyleSheet()
    story = []

    bn = brand_name()
    if not used_letterhead:
        logo_path = LOGO_PATH
        if os.path.exists(logo_path) and os.path.getsize(logo_path) > 0:
            try:
                from PIL import Image as PILImage
                pil_logo = PILImage.open(logo_path).convert("RGBA")
                pil_logo.thumbnail((240, 240))  # PDF is print-sized (28mm) -- no need for source-res pixels
                logo_buf = io.BytesIO(); pil_logo.save(logo_buf, format="PNG"); logo_buf.seek(0)
                story.append(RLImage(logo_buf, width=28 * mm, height=28 * mm, kind="proportional"))
                story.append(Spacer(1, 6))
            except Exception:
                pass

    title_style = ParagraphStyle("title", parent=styles["Title"], alignment=TA_CENTER,
                                  textColor=colors.HexColor("#101622"))
    story.append(Paragraph(f"{bn} — Asset Acknowledgement", title_style))

    tag_style = ParagraphStyle("tag", parent=styles["Normal"], alignment=TA_CENTER, fontSize=20,
                                fontName="Helvetica-Bold", textColor=colors.HexColor("#ff3b30"),
                                spaceBefore=6, spaceAfter=14)
    story.append(Paragraph(asset.get("AssetTag") or "—", tag_style))

    # Same field set/order/labels as the web "print asset" page, so the
    # emailed PDF and a manual print of the same asset read the same way.
    currency = asset.get("_currency") or "AED"
    try:
        price_str = f"{currency} {float(asset.get('Price') or 0):.2f}"
    except (TypeError, ValueError):
        price_str = f"{currency} 0.00"
    rows = [
        ["Asset ID", asset.get("AssetTag") or "—"],
        ["Asset Name", asset.get("Name") or "—"],
        ["Item Category", asset.get("Type") or "—"],
        ["Serial", asset.get("Serial") or "—"],
        ["Location", asset.get("Location") or "—"],
        ["Status", asset.get("Status") or "—"],
        ["Price", price_str],
        ["Warranty", str(asset.get("WarrantyMonths") if asset.get("WarrantyMonths") not in (None, "") else 0)],
        ["Signed Date", asset.get("NotesReceived") or "—"],
        ["Notes", asset.get("Notes") or "—"],
        ["Signed By", signer_name or "—"],
    ]
    if asset.get("EmployeeID"):
        rows += [
            ["Employee Name", asset.get("EmployeeName") or asset.get("EmployeeID")],
            ["Department", asset.get("Department") or "—"],
            ["Designation", asset.get("Designation") or "—"],
            ["Email", asset.get("Email") or "—"],
        ]
    t = Table(rows, colWidths=[45 * mm, 115 * mm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#555555")),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(t)
    story.append(Spacer(1, 18))

    story.append(Paragraph("Signature", ParagraphStyle(
        "sig-label", parent=styles["Normal"], fontSize=11, fontName="Helvetica-Bold", spaceAfter=6)))
    if sig_data_url and sig_data_url.startswith("data:image"):
        try:
            b64 = sig_data_url.split(",", 1)[1]
            sig_bytes = base64.b64decode(b64)
            from PIL import Image as PILImage
            pil = PILImage.open(io.BytesIO(sig_bytes))
            iw, ih = pil.size
            max_w, max_h = 80 * mm, 40 * mm
            scale = min(max_w / iw, max_h / ih) if iw and ih else 1
            story.append(RLImage(io.BytesIO(sig_bytes), width=iw * scale, height=ih * scale))
        except Exception:
            story.append(Paragraph("(signature image unavailable)", styles["Normal"]))
    else:
        story.append(Paragraph("(no signature captured)", styles["Normal"]))

    def _draw_letterhead_bg(cnv, _doc):
        if used_letterhead:
            cnv.saveState()
            cnv.drawImage(letterhead_path, 0, 0, width=A4[0], height=A4[1],
                           preserveAspectRatio=False, mask="auto")
            cnv.restoreState()

    doc.build(story, onFirstPage=_draw_letterhead_bg, onLaterPages=_draw_letterhead_bg)
    return buf.getvalue()

def _send_email_with_attachment(to_email, subject, body, attachment_bytes, attachment_name):
    import smtplib
    from email.message import EmailMessage
    c = conn(); cur = c.cursor()
    cur.execute("SELECT smtp_host, smtp_port, smtp_user, smtp_pass, smtp_from, app_name FROM Settings WHERE id=1")
    s = cur.fetchone() or {}; c.close()
    if not s.get("smtp_host") or not to_email:
        return False
    try:
        bn = s.get("app_name") or "IT-Vault"
        msg = EmailMessage(); msg["Subject"] = f"{bn}: {subject}"
        msg["From"] = s.get("smtp_from") or s.get("smtp_user")
        msg["To"] = to_email; msg.set_content(body + _email_footer(bn))
        msg.add_attachment(attachment_bytes, maintype="application", subtype="pdf", filename=attachment_name)
        with smtplib.SMTP(s["smtp_host"], int(s.get("smtp_port", 587) or 587), timeout=10) as sv:
            if s.get("smtp_user"): sv.starttls(); sv.login(s["smtp_user"], s.get("smtp_pass", ""))
            sv.send_message(msg)
        return True
    except Exception as e:
        print("email attachment send error:", e); return False

def _email_signed_asset_pdf(asset, signer_name, sig_data_url):
    """Sends the signed-acknowledgement PDF to the assigned employee/user and
    to every admin/staff account with an email on file -- fire-and-forget,
    never blocks or fails the acknowledgement itself. Returns True if a copy
    actually went to the assigned employee, so the sign page can promise
    "sent to your email" only when that's true."""
    try:
        pdf_bytes = _build_signed_asset_pdf(asset, signer_name, sig_data_url)
    except Exception as e:
        print("signed pdf build error:", e); return False
    fname = f"{(asset.get('AssetTag') or asset.get('_id') or 'asset')}_signed.pdf"
    tag = asset.get("AssetTag") or asset.get("_id", "")
    body = (f"'{asset.get('Name','')}' (Asset ID: {tag}) was acknowledged and signed by "
            f"{signer_name}. The signed copy is attached as a PDF.")
    sent_to = set()
    emailed_employee = False
    emp_email = _lookup_person_email(asset.get("EmployeeID") or "")
    if emp_email:
        emailed_employee = bool(_send_email_with_attachment(emp_email, f"Signed asset acknowledgement: {asset.get('Name','')}", body, pdf_bytes, fname))
        sent_to.add(emp_email.lower())
    try:
        c = conn(); cur = c.cursor()
        cur.execute("SELECT email FROM Users WHERE email<>''")
        admin_emails = [r["email"] for r in cur.fetchall()]
        c.close()
    except Exception:
        admin_emails = []
    for e in admin_emails:
        if e and e.lower() not in sent_to:
            _send_email_with_attachment(e, f"Signed asset acknowledgement: {asset.get('Name','')}", body, pdf_bytes, fname)
            sent_to.add(e.lower())
    return emailed_employee

@app.route("/api/assets/sign/approve", methods=["POST"])
def approve_asset():
    d = request.get_json(force=True) or {}
    tk = d.get("token",""); name = d.get("name","").strip()
    if not name: return jsonify({"error": "approver name required"}), 400
    data = _verify_token(tk)
    if not data: return jsonify({"error": "invalid or expired token"}), 400
    aid = data["asset_id"]
    c = conn(); cur = c.cursor()
    cur.execute("SELECT Name FROM Assets WHERE _id=%s", [aid]); a = cur.fetchone()
    if not a: c.close(); return jsonify({"error": "asset not found"}), 404
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    receivedBy = name
    notesReceived = datetime.now().strftime("%Y-%m-%d")
    sigData = (d.get("data") or "").strip()
    cur.execute("UPDATE Assets SET Status='Checked-Out', ReceivedBy=%s, Notes=CONCAT(IFNULL(Notes,''),'\\nAcknowledged by ',%s,' on ',NOW()), NotesReceived=%s, SignatureData=%s WHERE _id=%s",
                (receivedBy, name, notesReceived, sigData, aid))
    c.commit(); c.close()
    audit(session.get("user"), "ACKNOWLEDGE", aid, f"{name} acknowledged")
    emailed = False
    try:
        cc = conn(); ccur = cc.cursor()
        ccur.execute("SELECT * FROM Assets WHERE _id=%s", [aid]); full_asset = ccur.fetchone()
        if full_asset and full_asset.get("EmployeeID"):
            ccur.execute("SELECT EmployeeName, Department, Designation, Email FROM Employees WHERE EmployeeID=%s", [full_asset["EmployeeID"]])
            er = ccur.fetchone()
            if er:
                full_asset["EmployeeName"] = er.get("EmployeeName") or ""
                full_asset["Department"] = er.get("Department") or ""
                full_asset["Designation"] = er.get("Designation") or ""
                full_asset["Email"] = er.get("Email") or ""
        ccur.execute("SELECT currency FROM Settings WHERE id=1"); srow = ccur.fetchone() or {}
        full_asset["_currency"] = srow.get("currency") or "AED"
        cc.close()
        if full_asset:
            emailed = _email_signed_asset_pdf(full_asset, name, sigData)
    except Exception as e:
        print("signed pdf email error:", e)
    # tells the sign page whether it can honestly say a copy reached the
    # signer's own inbox (it only does if the asset has an employee with an
    # email on file and SMTP actually accepted it)
    return jsonify({"ok": True, "emailed": bool(emailed)})

@app.route("/api/assets/<aid>/signature")
@auth_required()
def asset_signature(aid):
    c = conn(); cur = c.cursor()
    cur.execute("SELECT SignatureData FROM Assets WHERE _id=%s", [aid])
    row = cur.fetchone(); c.close()
    data = (row or {}).get("SignatureData") or ""
    if not data: return jsonify({"ok": False, "error": "no signature"}), 404
    return jsonify({"ok": True, "data": data})

# ---------- network scanner ----------
import subprocess, re, concurrent.futures, socket, ipaddress

def _parse_scan_range(raw):
    """Accepts CIDR notation (e.g. '192.168.0.0/24', '172.16.0.0/22') or the
    older bare-prefix shorthand ('192.168.0' -> assumed /24). Returns the
    list of host IPs to sweep."""
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("enter a subnet, e.g. 192.168.0.0/24")
    if "/" not in raw:
        raw = raw.rstrip(".") + ".0/24"
    net = ipaddress.ip_network(raw, strict=False)
    if net.version != 4:
        raise ValueError("only IPv4 subnets are supported")
    if net.num_addresses > 4096:
        raise ValueError("subnet too large -- use /20 or smaller (max 4096 addresses)")
    return [str(ip) for ip in net.hosts()]

# MAC vendor (OUI) lookup -- IEEE's official public registry, bundled locally
# so scans work offline and no internal MAC/IP data ever leaves the network.
# This only identifies the manufacturer from the first 3 bytes of the MAC; a
# specific model can't be derived from a MAC address alone.
_OUI_VENDORS = {}
try:
    with open(os.path.join(BASE, "oui_vendors.json"), encoding="utf-8") as f:
        _OUI_VENDORS = json.load(f)
except Exception:
    _OUI_VENDORS = {}

def _mac_vendor(mac):
    prefix = re.sub(r"[^0-9A-Fa-f]", "", mac or "").upper()[:6]
    if len(prefix) < 6:
        return ""
    return _OUI_VENDORS.get(prefix, "")

def _is_real_host(ip, mac):
    """Filter the ARP table down to actual hosts.

    An ARP table also lists multicast groups (224.0.0.0/4, i.e. first octet
    224-239) and broadcast entries. Those are not devices and must never show
    up as something you can add as an asset.
    """
    # Compare on hex digits only, so this holds whichever separator the
    # platform's neighbour table used (dashes on Windows, colons elsewhere).
    bare = re.sub(r"[^0-9A-Fa-f]", "", mac or "").lower()
    if bare in ("ffffffffffff", "000000000000"):
        return False
    parts = ip.split(".")
    if len(parts) != 4:
        return False
    try:
        octets = [int(x) for x in parts]
    except ValueError:
        return False
    if not all(0 <= o <= 255 for o in octets):
        return False
    if 224 <= octets[0] <= 239:          # multicast
        return False
    if octets[0] in (0, 127):            # this-network / loopback
        return False
    if octets[3] in (0, 255):            # network / broadcast address
        return False
    if mac.lower().startswith("01-00-5e"):  # IPv4 multicast MAC prefix
        return False
    return True


_IS_WINDOWS = os.name == "nt"


def _norm_mac(mac):
    """One canonical MAC form (aa:bb:cc:dd:ee:ff).

    Windows `arp -a` prints dashes; Linux/macOS and `ip neigh` print colons.
    Normalising here keeps the broadcast filter and the OUI vendor lookup
    working identically on every platform.
    """
    hexes = re.sub(r"[^0-9A-Fa-f]", "", mac or "").lower()
    if len(hexes) != 12:
        return ""
    return ":".join(hexes[i:i + 2] for i in range(0, 12, 2))


def _arp_devices():
    """The neighbour table, on whichever platform we are running.

    The formats differ too much for one regex:
      Windows  `arp -a`    ->  192.168.0.7    aa-bb-cc-dd-ee-ff   dynamic
      Linux    `ip neigh`  ->  192.168.0.7 dev eth0 lladdr aa:bb:... REACHABLE
      Linux    `arp -an`   ->  ? (192.168.0.7) at aa:bb:... [ether] on eth0
      macOS    `arp -an`   ->  ? (192.168.0.7) at aa:bb:... on en0 ifscope
    """
    devs = {}

    def _add(ip, mac, typ):
        mac = _norm_mac(mac)
        if _is_real_host(ip, mac):
            devs[ip] = {"ip": ip, "mac": mac, "type": typ}

    def _run(cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout or ""
        except Exception:
            return ""

    if _IS_WINDOWS:
        out = _run(["arp", "-a"])
        for m in re.finditer(r"(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F-]{17})\s+(\w+)", out):
            _add(m.group(1), m.group(2), m.group(3))
        return devs

    # Linux first: `ip` exists on modern distros even where net-tools (which
    # provides `arp`) does not -- including slim container images.
    out = _run(["ip", "neigh", "show"])
    for m in re.finditer(
            r"(\d+\.\d+\.\d+\.\d+)\s+.*?lladdr\s+([0-9a-fA-F:]{17})(?:\s+(\w+))?", out):
        _add(m.group(1), m.group(2), (m.group(3) or "neighbour").lower())
    if devs:
        return devs

    # BSD/macOS/net-tools style fallback.
    out = _run(["arp", "-an"]) or _run(["arp", "-a"])
    for m in re.finditer(r"\((\d+\.\d+\.\d+\.\d+)\)\s+at\s+([0-9a-fA-F:]{17})", out):
        _add(m.group(1), m.group(2), "neighbour")
    return devs

def _ping_one(ip):
    """One ping, cross-platform.

    The flags are not portable: Windows wants `-n <count> -w <ms>`, Linux and
    macOS want `-c <count> -W <seconds>`. Handing the Windows form to Linux
    ping means "-n" (numeric output) with no count at all, so it pings forever
    and the subprocess timeout kills every probe -- which is exactly why a
    deep scan silently found nothing on Linux.
    """
    cmd = (["ping", "-n", "1", "-w", "700", ip] if _IS_WINDOWS
           else ["ping", "-c", "1", "-W", "1", ip])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
        out = (r.stdout or "").upper()
        # A zero exit code alone is not reliable on Windows ("Destination host
        # unreachable" still exits 0), so look for a real echo reply. Every
        # platform's ping prints a TTL ("TTL=" on Windows, "ttl=" elsewhere).
        alive = ("TTL=" in out) or ("REPLY FROM" in out) or (
            r.returncode == 0 and "BYTES FROM" in out)
        return ip if alive else None
    except Exception:
        return None

def _resolve_host(ip):
    # Reverse-DNS/NetBIOS lookup, best-effort -- many LAN devices won't
    # resolve, that's fine, we just leave the hostname blank for those.
    try:
        return ip, socket.gethostbyaddr(ip)[0].split(".")[0]
    except Exception:
        return ip, ""

@app.route("/api/scan")
@feature_required("tools.scan")
def network_scan():
    prefix = (request.args.get("prefix") or "").strip()
    deep = request.args.get("deep", "0") == "1"
    devs = _arp_devices()
    if deep and prefix:
        try:
            ips = _parse_scan_range(prefix)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        with concurrent.futures.ThreadPoolExecutor(max_workers=60) as ex:
            for ip in ex.map(_ping_one, ips):
                if ip and ip not in devs:
                    devs[ip] = {"ip": ip, "mac": "", "type": "discovered"}
    # pull hostnames best-effort, bounded so a few unresolvable devices can't
    # stall the whole scan
    for d in devs.values():
        d["host"] = ""
    if devs:
        with concurrent.futures.ThreadPoolExecutor(max_workers=30) as ex:
            futs = {ex.submit(_resolve_host, ip): ip for ip in devs}
            done, _pending = concurrent.futures.wait(futs, timeout=3)
            for f in done:
                ip, host = f.result()
                if host:
                    devs[ip]["host"] = host
    # brand/manufacturer from the MAC's OUI (a specific model can't be
    # determined from a MAC address, only the maker of the network card)
    for d in devs.values():
        d["vendor"] = _mac_vendor(d.get("mac"))
    result = sorted(devs.values(), key=lambda d: tuple(int(x) for x in d["ip"].split(".")))
    audit(session.get("user"), "SCAN", "", f"scanned {'deep ' if deep else ''}prefix={prefix or 'local'}: {len(result)} devices")
    return jsonify(result)

# ---------- backup / restore ----------
BACKUP_DIR = os.path.join(BASE, "backups")
os.makedirs(BACKUP_DIR, exist_ok=True)

def _dump_table(cur, table, cols=None):
    if cols is None:
        cur.execute(f"SHOW COLUMNS FROM `{table}`")
        cols = [r["Field"] for r in cur.fetchall()]
    cur.execute(f"SELECT {', '.join('`'+c+'`' for c in cols)} FROM `{table}`")
    rows = cur.fetchall()
    out = []
    for r in rows:
        vals = []
        for c in cols:
            v = r[c]
            if v is None:
                vals.append("NULL")
            elif isinstance(v, (bytes, bytearray)):
                # binary columns (the embedded logo blob) as raw text/quote
                # escaping corrupts on backslashes/control bytes -- hex
                # literals are the only safe way to round-trip them.
                vals.append("0x" + v.hex() if v else "NULL")
            elif isinstance(v, (int, float)):
                vals.append(str(v))
            else:
                # MariaDB treats backslash as an escape char inside '...' by
                # default, so a value with a literal backslash (a Windows
                # path in Notes, a DOMAIN\user LDAP bind) needs doubling too
                # -- quoting only single quotes let those corrupt the dump.
                esc = str(v).replace("\\", "\\\\").replace("'", "''")
                vals.append("'" + esc + "'")
        out.append(f"REPLACE INTO `{table}` ({', '.join('`'+c+'`' for c in cols)}) VALUES ({', '.join(vals)});")
    return out

def _prune_old_backups():
    """Keeps only the newest Settings.backup_retain backups on disk (default
    7) -- runs after every backup, scheduled or manual, so the folder never
    grows unbounded."""
    try:
        c = conn(); cur = c.cursor()
        cur.execute("SELECT backup_retain FROM Settings WHERE id=1"); row = cur.fetchone() or {}
        c.close()
        limit = int(row.get("backup_retain") or 7)
    except Exception:
        limit = 7
    if limit <= 0:
        return
    files = sorted([f for f in os.listdir(BACKUP_DIR) if f.endswith((".sql", ".zip"))],
                    key=lambda f: os.path.getmtime(os.path.join(BACKUP_DIR, f)), reverse=True)
    for f in files[limit:]:
        try:
            os.remove(os.path.join(BACKUP_DIR, f))
        except Exception:
            pass

def _dump_section(cur, table):
    """One table's worth of restore statements: a DELETE first so restoring
    this section actually reverts to the backup's exact state instead of just
    upserting rows on top of whatever is there now, then the REPLACE INTOs."""
    return [f"-- == {table} ==", f"DELETE FROM `{table}`;", *_dump_table(cur, table)]

# Every business table, so an "all"/"assets" backup is a complete,
# restorable snapshot. A factory wipe drops whatever the schema actually
# holds (read from information_schema), so there's no parallel list to
# keep in sync with this one.
ASSET_SCOPE_TABLES = [
    "Assets", "Checkouts", "Maintenance", "Contracts", "Employees",
    "Tickets", "TicketReplies", "Manufacturers", "Models", "Categories",
    "ContractTypes", "Departments", "Designations", "Locations", "Roles", "History",
]

BACKUP_BRANDING_FILES = ("logo.png", "letterhead.png")

def _run_backup(scope="all"):
    if scope not in ("config", "assets", "all"):
        scope = "all"
    c = conn(); cur = c.cursor()
    lines = [f"-- IT-Vault backup | scope={scope} | {datetime.now().strftime('%Y-%m-%d %H:%M')}"]
    include_branding = scope in ("config", "all")
    if scope in ("config", "all"):
        lines += _dump_section(cur, "Settings")
        lines += _dump_section(cur, "Users")
    if scope in ("assets", "all"):
        for t in ASSET_SCOPE_TABLES:
            lines += _dump_section(cur, t)
    if scope == "all":
        lines += _dump_section(cur, "AuditLog")
    c.close()
    sql_text = "\n".join(lines) + "\n"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if not include_branding:
        # assets-only scope never touches Settings, so there's no branding to
        # bundle -- keep it a plain .sql, same as before.
        fname = f"itvault_backup_{scope}_{stamp}.sql"
        with open(os.path.join(BACKUP_DIR, fname), "w", encoding="utf-8") as f:
            f.write(sql_text)
    else:
        # config/all scopes include Settings, so a backup calling itself
        # "whole" needs the logo and letterhead too -- those only ever live
        # on disk (has_letterhead is just a flag; letterhead is never stored
        # in the DB), so the SQL dump alone can't restore them. Bundle both
        # into a .zip alongside the dump; restore knows how to unpack it.
        fname = f"itvault_backup_{scope}_{stamp}.zip"
        with zipfile.ZipFile(os.path.join(BACKUP_DIR, fname), "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("dump.sql", sql_text)
            for bf in BACKUP_BRANDING_FILES:
                p = os.path.join(BASE, bf)
                try:
                    if os.path.getsize(p) > 0:
                        zf.write(p, bf)
                except Exception:
                    pass
    _prune_old_backups()
    return fname

@app.route("/api/admin/wipe", methods=["POST"])
@auth_required([ROLE_ADMIN])
def wipe_everything():
    """Danger Zone factory reset: password-gated, phrase-confirmed, takes an
    automatic full backup first so a wipe is always recoverable.

    Drops every table -- user accounts included -- rather than emptying them,
    so the instance comes back exactly like a fresh install: with no logins
    left, setup_needed() becomes true again and the app returns to the
    first-run wizard, where a new admin is created. Dropping rather than
    deleting also clears any stale column defaults the schema had picked up.

    The database and its MySQL user are deliberately NOT dropped: the wizard
    needs something to connect to, and recreating them would require
    credentials the app doesn't have."""
    d = request.get_json(force=True) or {}
    pw = d.get("password", "")
    confirm = (d.get("confirm") or "").strip().upper()
    if confirm != "WIPE EVERYTHING":
        return jsonify({"error": 'Type "WIPE EVERYTHING" exactly to confirm'}), 400
    c = conn(); cur = c.cursor()
    cur.execute("SELECT password FROM Users WHERE username=%s", [session.get("user")])
    row = cur.fetchone(); c.close()
    if not row or not verify_pw(pw, row["password"]):
        return jsonify({"error": "Incorrect password"}), 401
    backup_file = _run_backup("all")
    try:
        c = conn(); cur = c.cursor()
        cur.execute("SELECT TABLE_NAME AS t FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE()")
        tables = [r["t"] for r in cur.fetchall()]
        cur.execute("SET FOREIGN_KEY_CHECKS=0")
        for t in tables:
            cur.execute(f"DROP TABLE IF EXISTS `{t}`")
        cur.execute("SET FOREIGN_KEY_CHECKS=1")
        c.commit(); c.close()
        for fname in ("logo.png", "letterhead.png"):
            try:
                open(os.path.join(BASE, fname), "wb").close()
            except Exception:
                pass
    except Exception as e:
        return jsonify({"error": f"Wipe failed partway through: {e}. A pre-wipe backup was saved as {backup_file} -- restore it from Backup/Restore."}), 500
    # back to first-run: no schema, no logins, so drop the latch and this
    # session with it. There's no audit row to write -- the table is gone;
    # the pre-wipe backup is the record of what was there.
    global _setup_done
    _setup_done = False
    print(f"[itvault] FACTORY RESET by {session.get('user')} -- {len(tables)} tables dropped, "
          f"pre-wipe backup {backup_file}", flush=True)
    session.clear()
    return jsonify({"ok": True, "backup_file": backup_file, "setup_required": True})

@app.route("/api/version")
@auth_required()
def version_info():
    return jsonify({
        "version": APP_VERSION,
        "is_docker": IS_DOCKER,
        "repo": update_repo(),
        # False when DATA_DIR isn't a mounted volume: the saved database
        # pointer and session key would be lost the moment this container is
        # replaced, which is exactly how an update works.
        "data_persistent": _data_dir_persistent(),
    })

@app.route("/api/check-update", methods=["POST"])
@auth_required([ROLE_ADMIN])
def check_update():
    """Asks GitHub for the newest published release of this project and
    compares it to VERSION. Deliberately only ever runs when an admin presses
    the button -- this is a self-hosted tool and shouldn't phone home on its
    own. Nothing is downloaded or applied here: it reports what's available
    and how to upgrade, which for a container means pulling a new image."""
    repo = update_repo()
    if not repo or "/" not in repo:
        return jsonify({
            "ok": False,
            "current": APP_VERSION,
            "error": "This build has no update source baked in. Set "
                     "ITVAULT_UPDATE_REPO to a GitHub project (owner/repo) "
                     "that publishes releases.",
        }), 400

    import json as _json
    import urllib.error
    import urllib.request
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"IT-Vault/{APP_VERSION}",
    })
    try:
        # short timeout: an unreachable network must not tie up a worker
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = _json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return jsonify({"ok": True, "current": APP_VERSION, "latest": None,
                            "update_available": False, "is_docker": IS_DOCKER,
                            "note": "No releases published yet for "
                                    f"{repo} -- nothing to update to."})
        return jsonify({"ok": False, "current": APP_VERSION,
                        "error": f"GitHub returned HTTP {e.code}"}), 502
    except Exception as e:
        return jsonify({"ok": False, "current": APP_VERSION,
                        "error": f"Could not reach GitHub: {e}"}), 502

    latest = (data.get("tag_name") or data.get("name") or "").strip()
    newer = bool(latest) and _version_tuple(latest) > _version_tuple(APP_VERSION)
    # The command is returned separately from the prose so the UI can offer
    # a one-click copy. It is deliberately NOT executed here: applying it
    # means replacing the very container this process runs in, which a
    # container cannot do to itself without being handed the host's Docker
    # socket -- root-equivalent control of the machine, in exchange for
    # saving one command. Watchtower (see the README) is the safe way to
    # make updates hands-off.
    cmd = ""
    method = _update_method()
    if newer and IS_DOCKER:
        cmd = "docker compose pull && docker compose up -d"
        how = ("You're running the container image. Pull the new image and "
               "recreate the container:\n\n"
               f"    {cmd}\n\n"
               "Your database, invoices and backups live in named volumes, "
               "so they survive the swap. To have this happen automatically "
               "whenever a release lands, run Watchtower alongside IT-Vault "
               "-- the README has the one-liner.")
    elif newer:
        cmd = "git pull && pip install -r requirements.txt"
        how = ("You're running from source. Fetch the new release, install "
               "any new requirements, and restart:\n\n"
               f"    {cmd}\n\n"
               "then restart the app. The schema migrates itself on startup.")
    else:
        how = ""
    return jsonify({
        "ok": True,
        "current": APP_VERSION,
        "latest": latest or None,
        "update_available": newer,
        "is_docker": IS_DOCKER,
        "release_url": data.get("html_url") or "",
        "notes": (data.get("body") or "")[:2000],
        "how_to_update": how,
        "update_command": cmd,
        "update_method": method,
        "can_one_click": bool(newer and method),
    })

@app.route("/api/update/apply", methods=["POST"])
@auth_required([ROLE_ADMIN])
def update_apply():
    """Apply the available update in one click, where that is possible
    without this process taking control of the host. See _watchtower()."""
    method = _update_method()

    if method == "watchtower":
        url, token = _watchtower()
        import urllib.error, urllib.request
        req = urllib.request.Request(
            url + "/v1/update", data=b"", method="POST",
            headers={"Authorization": "Bearer " + token,
                     "User-Agent": f"IT-Vault/{APP_VERSION}"})
        try:
            # generous timeout: this covers pulling the image layers
            with urllib.request.urlopen(req, timeout=120) as resp:
                resp.read()
        except urllib.error.HTTPError as e:
            return jsonify({"ok": False,
                            "error": f"Watchtower refused the request (HTTP {e.code}). "
                                     "Check ITVAULT_WATCHTOWER_TOKEN matches its "
                                     "WATCHTOWER_HTTP_API_TOKEN."}), 502
        except Exception as e:
            return jsonify({"ok": False,
                            "error": f"Could not reach Watchtower at {url}: {e}"}), 502
        audit(session.get("user"), "UPDATE_APPLY", "", f"via=watchtower from={APP_VERSION}")
        return jsonify({"ok": True, "method": "watchtower", "restarting": True,
                        "message": "Watchtower is pulling the new image and "
                                   "recreating IT-Vault. This page reconnects "
                                   "on its own once the new version is up."})

    if method == "source":
        steps = []
        for label, cmd in (("git pull", ["git", "pull", "--ff-only"]),
                           ("pip install", [sys.executable, "-m", "pip", "install",
                                            "-q", "-r", "requirements.txt"])):
            try:
                pr = subprocess.run(cmd, cwd=BASE, capture_output=True,
                                    text=True, timeout=600)
            except Exception as e:
                return jsonify({"ok": False, "log": "\n\n".join(steps),
                                "error": f"{label} could not run: {e}"}), 500
            steps.append(("$ " + " ".join(cmd) + "\n"
                          + (pr.stdout or "") + (pr.stderr or "")).strip())
            if pr.returncode != 0:
                # nothing is restarted on failure, so the running version and
                # its dependencies stay exactly as they were
                return jsonify({"ok": False, "log": "\n\n".join(steps),
                                "error": f"{label} failed -- nothing was restarted, "
                                         "so the running version is unchanged."}), 500
        audit(session.get("user"), "UPDATE_APPLY", "", f"via=source from={APP_VERSION}")
        threading.Thread(target=_restart_self, daemon=True).start()
        return jsonify({"ok": True, "method": "source", "restarting": True,
                        "log": "\n\n".join(steps),
                        "message": "Update pulled. Restarting IT-Vault -- this "
                                   "page reconnects in a few seconds."})

    if IS_DOCKER:
        return jsonify({"ok": False, "needs_watchtower": True,
                        "error": "One-click updating isn't wired up yet. IT-Vault "
                                 "can't replace its own container, so it asks "
                                 "Watchtower to do it: start Watchtower with an "
                                 "HTTP API token (the README has the one-liner) "
                                 "and set ITVAULT_WATCHTOWER_TOKEN to the same "
                                 "value. Until then, run the command above."}), 400
    return jsonify({"ok": False,
                    "error": "This install isn't a git checkout, so there's "
                             "nothing to pull. Download the new release and "
                             "replace the files."}), 400

@app.route("/api/backup")
@feature_required("tools.backup")
def backup():
    scope = (request.args.get("scope") or "all").lower()
    if scope not in ("config", "assets", "all"):
        scope = "all"
    fname = _run_backup(scope)
    audit(session.get("user"), "BACKUP", "", f"scope={scope} file={fname}")
    mt = "application/zip" if fname.endswith(".zip") else "application/sql"
    return send_from_directory(BACKUP_DIR, fname, as_attachment=True,
                                mimetype=mt,
                                download_name=fname)

@app.route("/api/backups")
@feature_required("tools.backup")
def list_backups():
    # newest-first by actual file time, not filename string -- sorting by name
    # put every "config" backup ahead of a same-day "all" one since "c" > "a".
    files = sorted([f for f in os.listdir(BACKUP_DIR) if f.endswith((".sql", ".zip"))],
                    key=lambda f: os.path.getmtime(os.path.join(BACKUP_DIR, f)), reverse=True)
    out = []
    for f in files:
        try:
            # filenames look like itvault_backup_<scope>_<YYYYMMDD>_<HHMMSS>.sql
            ts = "_".join(f.rsplit(".", 1)[0].split("_")[-2:])
            dt = datetime.strptime(ts, "%Y%m%d_%H%M%S").strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            # fall back to the file's actual mtime rather than showing "?"
            try:
                dt = datetime.fromtimestamp(os.path.getmtime(os.path.join(BACKUP_DIR, f))).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                dt = "?"
        scope = "all"
        for s in ("config", "assets"):
            if f"_{s}_" in f: scope = s
        out.append({"file": f, "scope": scope, "created": dt, "size": os.path.getsize(os.path.join(BACKUP_DIR, f))})
    return jsonify(out)

BACKUP_FNAME_RE = re.compile(r"^itvault_backup_(all|config|assets)_\d{8}_\d{6}\.(sql|zip)$")

@app.route("/api/backups/<fname>/download")
@auth_required([ROLE_ADMIN])
def download_backup(fname):
    if not BACKUP_FNAME_RE.match(fname):
        return jsonify({"error": "invalid filename"}), 400
    if not os.path.exists(os.path.join(BACKUP_DIR, fname)):
        return jsonify({"error": "not found"}), 404
    mt = "application/zip" if fname.endswith(".zip") else "application/sql"
    return send_from_directory(BACKUP_DIR, fname, as_attachment=True,
                                mimetype=mt, download_name=fname)

@app.route("/api/backups/<fname>", methods=["DELETE"])
@auth_required([ROLE_ADMIN])
def delete_backup(fname):
    if not BACKUP_FNAME_RE.match(fname):
        return jsonify({"error": "invalid filename"}), 400
    fpath = os.path.join(BACKUP_DIR, fname)
    if not os.path.exists(fpath):
        return jsonify({"error": "not found"}), 404
    os.remove(fpath)
    audit(session.get("user"), "BACKUP_DELETE", "", f"file={fname}")
    return jsonify({"ok": True})

def _split_sql_statements(content):
    """Split a backup file into individual statements on ';', but only
    outside of single-quoted string literals -- a naive content.split(';')
    corrupts the very next statement whenever a dumped value (Notes,
    Address, ...) happens to contain a semicolon of its own, which was
    silently breaking real-world restores."""
    stmts, buf, in_str, i, n = [], [], False, 0, len(content)
    while i < n:
        ch = content[i]
        buf.append(ch)
        if ch == "'":
            if in_str and i + 1 < n and content[i + 1] == "'":
                buf.append(content[i + 1]); i += 1  # escaped '' -- stays in-string
            else:
                in_str = not in_str
        elif ch == ";" and not in_str:
            stmts.append("".join(buf[:-1])); buf = []
        i += 1
    tail = "".join(buf).strip()
    if tail:
        stmts.append(tail)
    return stmts

def _apply_restore_sql(content):
    """Runs every statement in a backup file inside one transaction -- either
    the whole restore lands or none of it does, so a bad file never leaves
    the database half-migrated."""
    c = conn(); cur = c.cursor()
    applied = 0
    for stmt in _split_sql_statements(content):
        s = stmt.strip()
        if not s or s.startswith("--"): continue
        try:
            cur.execute(s); applied += 1
        except Exception as e:
            c.rollback(); c.close()
            return None, f"restore failed near: {s[:60]} -> {e}"
    c.commit(); c.close()
    return applied, None

def _apply_restore_bytes(data, filename=""):
    """Accepts either a legacy plain-SQL backup or the newer .zip bundle (a
    dump.sql plus logo.png/letterhead.png -- those never lived in the
    database, so a "whole" backup has to carry the actual files) and applies
    whichever it is. Branding files are written to disk before the SQL runs,
    so a restore that fails partway through the SQL still leaves them in a
    consistent, already-swapped state rather than a half-updated one."""
    is_zip = filename.lower().endswith(".zip") or data[:2] == b"PK"
    if not is_zip:
        return _apply_restore_sql(data.decode("utf-8", "replace"))
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()
            if "dump.sql" not in names:
                return None, "invalid backup: missing dump.sql in archive"
            sql_text = zf.read("dump.sql").decode("utf-8", "replace")
            branding = {bf: zf.read(bf) for bf in BACKUP_BRANDING_FILES if bf in names}
    except zipfile.BadZipFile:
        return None, "invalid backup: not a valid .zip archive"
    applied, err = _apply_restore_sql(sql_text)
    if err:
        return None, err
    for bf, data_bytes in branding.items():
        try:
            with open(os.path.join(BASE, bf), "wb") as fp:
                fp.write(data_bytes)
        except Exception:
            pass
    return applied, None

@app.route("/api/restore", methods=["POST"])
@auth_required([ROLE_ADMIN])
def restore():
    if "file" not in request.files:
        return jsonify({"error": "no file"}), 400
    f = request.files["file"]
    if not (f.filename.endswith(".sql") or f.filename.endswith(".zip")):
        return jsonify({"error": "only .sql or .zip backup allowed"}), 400
    data = f.read()
    applied, err = _apply_restore_bytes(data, f.filename)
    if err:
        return jsonify({"error": err}), 400
    audit(session.get("user"), "RESTORE", "", f"file={f.filename} statements={applied}")
    return jsonify({"ok": True, "statements": applied})

@app.route("/api/backups/<fname>/restore", methods=["POST"])
@auth_required([ROLE_ADMIN])
def restore_from_backup(fname):
    if not BACKUP_FNAME_RE.match(fname):
        return jsonify({"error": "invalid filename"}), 400
    fpath = os.path.join(BACKUP_DIR, fname)
    if not os.path.exists(fpath):
        return jsonify({"error": "not found"}), 404
    with open(fpath, "rb") as fp:
        data = fp.read()
    applied, err = _apply_restore_bytes(data, fname)
    if err:
        return jsonify({"error": err}), 400
    audit(session.get("user"), "RESTORE", "", f"file={fname} statements={applied}")
    return jsonify({"ok": True, "statements": applied})

# ---------- frontend ----------
@app.after_request
def _no_cache_frontend(resp):
    """index.html / app.js / style.css are edited in place, and browsers were
    happily serving stale copies -- which made real fixes look like they had
    not been applied. Never cache the app shell, and always state the charset
    explicitly so multi-byte characters (emoji in the sidebar) decode."""
    mt = (resp.mimetype or "")
    if mt in ("text/html", "text/css", "text/javascript", "application/javascript"):
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        if "charset" not in resp.headers.get("Content-Type", "").lower():
            resp.headers["Content-Type"] = mt + "; charset=utf-8"
    return resp


SETUP_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>IT-Vault — Setup</title>
<style>
  :root{ --bg:#000000; --card:#0c0f18; --line:#1c2130; --acc:#ff3b30;
         --txt:#e6edf6; --mut:#8a98b0;
         --font:'Inter','Segoe UI',system-ui,-apple-system,Arial,sans-serif; }
  *{box-sizing:border-box}
  body{margin:0;font-family:var(--font);background:var(--bg);color:var(--txt);
       min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px}
  .card{width:100%;max-width:560px;background:var(--card);border:1px solid var(--line);
        border-radius:12px;padding:32px}
  h1{font-size:21px;margin:0 0 4px;letter-spacing:-.01em}
  .sub{color:var(--mut);font-size:14px;line-height:1.55;margin:0 0 22px}
  .steps{display:flex;gap:8px;margin-bottom:22px}
  .step{flex:1;height:3px;background:var(--line);border-radius:2px}
  .step.on{background:var(--acc)}
  label{display:block;font-size:11px;font-weight:700;letter-spacing:.4px;
        text-transform:uppercase;color:var(--mut);margin:14px 0 6px}
  input{width:100%;background:#05070c;border:1px solid var(--line);color:var(--txt);
        border-radius:8px;padding:11px 12px;font-size:14px;font-family:inherit}
  input:focus{outline:none;border-color:var(--acc)}
  .row{display:flex;gap:12px}.row>div{flex:1}
  button{margin-top:22px;width:100%;background:var(--acc);color:#fff;border:0;
         border-radius:8px;padding:12px;font-size:14px;font-weight:700;cursor:pointer;font-family:inherit}
  button:disabled{opacity:.55;cursor:default}
  .msg{margin-top:14px;font-size:13.5px;line-height:1.5;display:none}
  .msg.err{color:#ff6b6b;display:block}.msg.ok{color:#3ddc97;display:block}
  .msg.info{color:var(--mut);display:block}
  .hide{display:none}
</style></head><body>
<div class="card">
  <h1>IT-Vault setup</h1>
  <p class="sub" id="sub">Point this instance at its database. Nothing is stored until the connection works.</p>
  <div class="steps"><div class="step on" id="s1"></div><div class="step" id="s2"></div></div>

  <div id="stepDb">
    <div class="row">
      <div><label>Database host</label><input id="db_host" value="__DB_HOST__" placeholder="db"></div>
      <div style="max-width:120px"><label>Port</label><input id="db_port" value="__DB_PORT__"></div>
    </div>
    <label>Database name</label><input id="db_name" value="__DB_NAME__">
    <label>Database user</label><input id="db_user" value="__DB_USER__">
    <label>Database password</label><input id="db_pass" type="password">
    <button id="testBtn">Test connection &amp; continue</button>
  </div>

  <div id="stepAdmin" class="hide">
    <label>Admin username</label><input id="ad_user" value="admin" autocomplete="username">
    <label>Admin password</label><input id="ad_pass" type="password" autocomplete="new-password">
    <label>Confirm password</label><input id="ad_pass2" type="password" autocomplete="new-password">
    <button id="finishBtn">Create admin &amp; finish</button>
  </div>

  <div class="msg" id="msg"></div>
</div>
<script>
const $=id=>document.getElementById(id);
const msg=(t,cls)=>{ const m=$('msg'); m.textContent=t; m.className='msg '+(cls||'info'); };
let dbCfg=null;

$('testBtn').onclick=async()=>{
  const cfg={ db_host:$('db_host').value.trim(), db_port:parseInt($('db_port').value,10)||3306,
              db_name:$('db_name').value.trim(), db_user:$('db_user').value.trim(),
              db_pass:$('db_pass').value };
  if(!cfg.db_host||!cfg.db_name||!cfg.db_user){ msg('Host, database name and user are required.','err'); return; }
  $('testBtn').disabled=true; msg('Testing connection…','info');
  try{
    const r=await fetch('/api/setup/test-db',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(cfg)});
    const j=await r.json();
    if(!j.ok){ msg(j.msg||'Could not connect.','err'); $('testBtn').disabled=false; return; }
    dbCfg=cfg; msg(j.msg||'Connected.','ok');
    $('stepDb').classList.add('hide'); $('stepAdmin').classList.remove('hide');
    $('s2').classList.add('on');
    $('sub').textContent='Create the first administrator account for this instance.';
  }catch(e){ msg('Could not reach the server: '+e.message,'err'); $('testBtn').disabled=false; }
};

$('finishBtn').onclick=async()=>{
  const u=$('ad_user').value.trim(), p=$('ad_pass').value, p2=$('ad_pass2').value;
  if(!u){ msg('Username is required.','err'); return; }
  if(p.length<8){ msg('Use at least 8 characters for the admin password.','err'); return; }
  if(p!==p2){ msg('The two passwords do not match.','err'); return; }
  $('finishBtn').disabled=true; msg('Creating database schema and admin account…','info');
  try{
    const r=await fetch('/api/setup/complete',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify(Object.assign({},dbCfg,{admin_user:u,admin_pass:p}))});
    const j=await r.json();
    if(!j.ok){ msg(j.error||'Setup failed.','err'); $('finishBtn').disabled=false; return; }
    msg('Setup complete — taking you to the sign-in page…','ok');
    setTimeout(()=>{ location.href='/'; }, 1200);
  }catch(e){ msg('Setup failed: '+e.message,'err'); $('finishBtn').disabled=false; }
};
</script></body></html>"""

@app.route("/setup")
def setup_page():
    if not setup_needed():
        return redirect("/")
    # Prefill from the config this instance already has, so a factory reset
    # comes back to fields that are correct rather than to the Docker
    # defaults. The password is deliberately NOT prefilled: while setup is
    # pending this page is unauthenticated, and putting a live database
    # password into its HTML would hand it to whoever loads it first.
    from html import escape
    cfg = load_config()
    html = (SETUP_HTML
            .replace("__DB_HOST__", escape(str(cfg.get("db_host") or os.environ.get("DB_HOST", "db")), quote=True))
            .replace("__DB_PORT__", escape(str(cfg.get("db_port") or os.environ.get("DB_PORT", "3306")), quote=True))
            .replace("__DB_NAME__", escape(str(cfg.get("db_name") or os.environ.get("DB_NAME", "itvault")), quote=True))
            .replace("__DB_USER__", escape(str(cfg.get("db_user") or os.environ.get("DB_USER", "itvault")), quote=True)))
    return Response(html, mimetype="text/html")

@app.route("/api/setup/test-db", methods=["POST"])
def setup_test_db():
    """Unauthenticated ON PURPOSE -- there is no account to authenticate
    against yet. Guarded by setup_needed(), which stops being true the moment
    a reachable database has a user in it, so this closes permanently after
    the first successful setup and cannot be reopened over the network."""
    if not setup_needed():
        return jsonify({"ok": False, "msg": "Setup has already been completed"}), 403
    d = request.get_json(force=True) or {}
    try:
        c = pymysql.connect(host=d.get("db_host", "db"), port=int(d.get("db_port", 3306)),
                            user=d.get("db_user", ""), password=d.get("db_pass", ""),
                            database=d.get("db_name", ""), charset="utf8mb4",
                            cursorclass=pymysql.cursors.DictCursor, connect_timeout=8)
        c.close()
        return jsonify({"ok": True, "msg": f"Connected to {d.get('db_host')}:{d.get('db_port')}/{d.get('db_name')}"})
    except Exception as e:
        return jsonify({"ok": False, "msg": _db_error_help(e, d.get("db_host", ""))}), 400

@app.route("/api/setup/complete", methods=["POST"])
def setup_complete():
    if not setup_needed():
        return jsonify({"ok": False, "error": "Setup has already been completed"}), 403
    d = request.get_json(force=True) or {}
    admin_user = (d.get("admin_user") or "").strip()
    admin_pass = d.get("admin_pass") or ""
    if not admin_user:
        return jsonify({"ok": False, "error": "Admin username is required"}), 400
    if len(admin_pass) < 8:
        return jsonify({"ok": False, "error": "Admin password must be at least 8 characters"}), 400
    try:
        # persist the DB config first so conn() (and the pool) pick it up
        save_db_config(d.get("db_host", "db"), int(d.get("db_port", 3306)),
                       d.get("db_name", ""), d.get("db_user", ""), d.get("db_pass", ""))
        global _pool_key
        _pool_key = None  # force the pool to rebuild against the new config
        init_db()
        migrate_schema()
        c = conn(); cur = c.cursor()
        cur.execute("SELECT COUNT(*) AS n FROM Users")
        if (cur.fetchone() or {}).get("n"):
            # init_db() seeds a default admin when the table is empty; replace
            # it with the credentials actually chosen here rather than leaving
            # the well-known default in place
            cur.execute("DELETE FROM Users")
        cur.execute("INSERT INTO Users (username, password, role, display, email) VALUES (%s,%s,%s,%s,%s)",
                    (admin_user, hash_pw(admin_pass), ROLE_ADMIN, admin_user, ""))
        c.commit(); c.close()
    except Exception as e:
        return jsonify({"ok": False, "error": f"Setup failed: {e}"}), 500
    global _setup_done
    _setup_done = True
    audit(admin_user, "SETUP", "", "first-run setup completed")
    return jsonify({"ok": True})

def _start_session(username, role, display, remember):
    """Establishes a logged-in session. `remember` decides whether it carries
    an idle expiry at all: without one it lasts until the user logs out."""
    session["user"] = username
    session["role"] = role
    session["display"] = display
    session.permanent = True
    if remember:
        session.pop("exp", None)
    else:
        session["exp"] = time.time() + SHORT_SESSION_SECONDS

@app.before_request
def _enforce_session_timeout():
    """The idle timeout, enforced per session rather than app-wide. A session
    with no "exp" is a "keep me signed in" one and never idles out; the rest
    slide forward on each request and are dropped once they go stale."""
    if not session.get("user"):
        return None
    exp = session.get("exp")
    if exp is None:
        return None
    if time.time() > float(exp):
        session.clear()
        if request.path.startswith("/api/"):
            return jsonify({"error": "Session expired -- please sign in again"}), 401
        return None  # page loads fall through and land on the login screen
    session["exp"] = time.time() + SHORT_SESSION_SECONDS
    return None

@app.before_request
def _force_setup_first():
    """While unconfigured, send page loads to the wizard. API calls get a
    JSON 503 instead of an HTML redirect so clients (and the Android app)
    fail clearly rather than parsing a login page as data."""
    if not setup_needed():
        return None
    p = request.path
    if p.startswith("/api/setup/") or p == "/setup" or p.startswith("/static/"):
        return None
    if p.startswith("/api/"):
        return jsonify({"error": "IT-Vault is not set up yet", "setup_required": True}), 503
    if p in ("/", "/index.html", "/login.html"):
        return redirect("/setup")
    return None

@app.route("/")
def index():
    if not session.get("user"):
        # a valid persistent API key (set as a cookie by the Android app right
        # after login) lets the WebView land straight on index.html instead
        # of the login page, without ever needing a fresh session cookie
        if not _resolve_session_from_api_key():
            return send_from_directory(BASE, "login.html")
    return send_from_directory(BASE, "index.html")

@app.route("/<path:p>")
def static_files(p):
    if p in ("login.html", "index.html", "style.css", "app.js"):
        return send_from_directory(BASE, p)
    return jsonify({"error": "not found"}), 404

# ---------- LDAP auto-sync scheduler (background thread) ----------

def _ldap_auto_sync_loop():
    while True:
        time.sleep(1800)  # sync every 30 minutes
        try:
            row = _ldap_settings()
            if row.get("ldap_server") and row.get("ldap_bind_user") and row.get("ldap_bind_pass") and row.get("ldap_base_dn"):
                ldap_sync_all(row)
                print("[itguy] LDAP auto-sync completed")
        except Exception as e:
            print("[itguy] LDAP auto-sync failed:", e)

_threading_started = False
def start_ldap_scheduler():
    global _threading_started
    if _threading_started:
        return
    _threading_started = True
    t = threading.Thread(target=_ldap_auto_sync_loop, daemon=True)
    t.start()

# ---------- scheduled backups (daily / weekly, background thread) ----------
def _maybe_run_scheduled_backup():
    c = conn(); cur = c.cursor()
    cur.execute("SELECT backup_schedule, backup_scope, backup_last_run FROM Settings WHERE id=1")
    row = cur.fetchone() or {}; c.close()
    sched = (row.get("backup_schedule") or "off").lower()
    if sched not in ("daily", "weekly"):
        return
    last = row.get("backup_last_run") or ""
    due = True
    if last:
        try:
            last_dt = datetime.strptime(last, "%Y-%m-%d %H:%M:%S")
            hours_needed = 24 if sched == "daily" else 24 * 7
            due = (datetime.now() - last_dt).total_seconds() >= hours_needed * 3600
        except Exception:
            due = True
    if not due:
        return
    scope = (row.get("backup_scope") or "all").lower()
    fname = _run_backup(scope)
    c2 = conn(); cur2 = c2.cursor()
    cur2.execute("UPDATE Settings SET backup_last_run=%s WHERE id=1", [datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
    c2.commit(); c2.close()
    audit("system", "BACKUP", "", f"scheduled ({sched}) scope={scope} file={fname}")
    print(f"[itguy] scheduled backup completed: {fname}")

def _backup_scheduler_loop():
    while True:
        try:
            _maybe_run_scheduled_backup()
        except Exception as e:
            print("[itguy] backup scheduler failed:", e)
        time.sleep(3600)  # check hourly -- actual due-ness is decided by backup_last_run

_backup_thread_started = False
def start_backup_scheduler():
    global _backup_thread_started
    if _backup_thread_started:
        return
    _backup_thread_started = True
    t = threading.Thread(target=_backup_scheduler_loop, daemon=True)
    t.start()

# ---------- contract / license / subscription expiry notifications ----------
def _notify_contract_expiring(ct, days_left):
    when = "today" if days_left == 0 else f"in {days_left} day{'s' if days_left != 1 else ''}"
    subj = f"Contract expiring {when}: {ct.get('name','')}"
    body = (f"The following contract/subscription/license is expiring {when}.\n\n"
            f"Name: {ct.get('name','')}\n"
            f"Vendor: {ct.get('vendor') or '—'}\n"
            f"Type: {ct.get('type') or '—'}\n"
            f"End Date: {ct.get('end_date') or '—'}\n")
    recipients = set()
    emp_email = _lookup_person_email(ct.get("employee_id") or "")
    if emp_email:
        _send_simple_email(emp_email, subj, body); recipients.add(emp_email.lower())
    vend_email = (ct.get("vendor_email") or "").strip()
    if vend_email and vend_email.lower() not in recipients:
        _send_simple_email(vend_email, subj, body); recipients.add(vend_email.lower())
    try:
        c = conn(); cur = c.cursor()
        cur.execute("SELECT email FROM Users WHERE email<>''")
        admin_emails = [r["email"] for r in cur.fetchall()]
        c.close()
    except Exception:
        admin_emails = []
    for e in admin_emails:
        if e and e.lower() not in recipients:
            _send_simple_email(e, subj, body); recipients.add(e.lower())

def check_contract_expiry():
    """Emails the vendor + assigned employee + admin team when a contract is
    within 3 days of its end_date -- once per expiry date (re-armed
    automatically if the contract is edited, since PUT resets
    expiry_notified_at)."""
    try:
        c = conn(); cur = c.cursor()
        cur.execute("SELECT * FROM Contracts WHERE is_deleted=0 AND end_date<>''")
        rows = cur.fetchall(); c.close()
    except Exception as e:
        print("[itguy] contract expiry check failed:", e); return
    today = datetime.now().date()
    for ct in rows:
        end_raw = (ct.get("end_date") or "").strip()
        if not end_raw:
            continue
        try:
            end_d = datetime.strptime(end_raw[:10], "%Y-%m-%d").date()
        except Exception:
            continue
        days_left = (end_d - today).days
        if days_left < 0 or days_left > 3:
            continue
        if (ct.get("expiry_notified_at") or "") == end_raw:
            continue
        try:
            _notify_contract_expiring(ct, days_left)
            c2 = conn(); cur2 = c2.cursor()
            cur2.execute("UPDATE Contracts SET expiry_notified_at=%s WHERE id=%s", (end_raw, ct["id"]))
            c2.commit(); c2.close()
        except Exception as e:
            print("[itguy] contract expiry notify failed:", e)

def _contract_expiry_loop():
    while True:
        try:
            check_contract_expiry()
        except Exception as e:
            print("[itguy] contract expiry loop error:", e)
        time.sleep(21600)  # check every 6 hours

_contract_expiry_thread_started = False
def start_contract_expiry_scheduler():
    global _contract_expiry_thread_started
    if _contract_expiry_thread_started:
        return
    _contract_expiry_thread_started = True
    t = threading.Thread(target=_contract_expiry_loop, daemon=True)
    t.start()

if __name__ == "__main__":
    init_db()
    migrate_schema()
    start_ldap_scheduler()
    start_backup_scheduler()
    start_contract_expiry_scheduler()
    print("IT-Vault (MariaDB) -> http://localhost:5000  (admin: %s)" % ADMIN_USER)
    app.run(host="0.0.0.0", port=5000, debug=False)
