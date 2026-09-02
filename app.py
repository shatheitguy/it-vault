"""
IT Guy - The Assets Manager — Flask + MariaDB backend.
Roles: admin (full), read-write (assets CRUD), read-only (view + own password).
Docker-ready. No Access DB.
"""
import os, io, json, hashlib, uuid, secrets, time, base64, re
from datetime import timedelta, datetime
from urllib.parse import quote, unquote
from flask import Flask, request, jsonify, Response, session, send_from_directory
import pymysql
from openpyxl import Workbook, load_workbook
import ldap3

BASE = os.path.dirname(os.path.abspath(__file__))
INVOICE_DIR = os.path.join(BASE, "invoices")
os.makedirs(INVOICE_DIR, exist_ok=True)

# ---- persistent DB config (nexus_config.json) ----
# Lets you point the app at a different MariaDB container/server from the UI.
CONFIG_PATH = os.path.join(BASE, "nexus_config.json")
def load_config():
    cfg = {}
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH) as f:
                cfg = json.load(f) or {}
    except Exception:
        cfg = {}
    return cfg
_cfg = load_config()
DB_HOST = _cfg.get("db_host", os.environ.get("DB_HOST", "127.0.0.1"))
DB_PORT = int(_cfg.get("db_port", os.environ.get("DB_PORT", 3306)))
DB_NAME = _cfg.get("db_name", os.environ.get("DB_NAME", "itguy_assets"))
DB_USER = _cfg.get("db_user", os.environ.get("DB_USER", "itguy"))
DB_PASS = _cfg.get("db_pass", os.environ.get("DB_PASS", "itguypass"))
def save_db_config(h, p, n, u, pw):
    global DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS = h, int(p), n, u, pw
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump({"db_host": h, "db_port": int(p), "db_name": n, "db_user": u, "db_pass": pw}, f, indent=2)
    except Exception:
        pass
SECRET = os.environ.get("ITGUY_SECRET", "itguy-local-secret-change-me")
ADMIN_USER = os.environ.get("ITGUY_ADMIN", "admin")
ADMIN_PASS = os.environ.get("ITGUY_ADMIN_PASS", "admin123")

COLUMNS = ["Name", "Type", "Serial", "MacAddress", "Location", "Status", "Manufacturer", "Model", "ReceivedBy", "NotesReceived", "Note", "PurchaseDate", "WarrantyMonths", "Price", "EmployeeID"]
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
STATUSES = ["New", "In Use", "Available", "Checked-Out", "Under-Maintenance", "Storage", "Worn", "Retired", "Out of Service"]
# role groups
ROLE_VIEW = "read-only"
ROLE_EDIT = "read-write"
ROLE_ADMIN = "admin"
ROLES = [ROLE_ADMIN, ROLE_EDIT, ROLE_VIEW]

app = Flask(__name__, static_folder=None)
app.secret_key = SECRET
app.permanent_session_lifetime = timedelta(minutes=5)

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
def conn():
    return pymysql.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS,
                            database=DB_NAME, charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor)

def init_db():
    c = conn(); cur = c.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS Assets (
        _id VARCHAR(40) PRIMARY KEY,
        Name VARCHAR(255), Type VARCHAR(255), Serial VARCHAR(255), Location VARCHAR(255),
        Status VARCHAR(255), ReceivedBy VARCHAR(255), NotesReceived TEXT, Notes TEXT, Note TEXT, PurchaseDate VARCHAR(255),
        WarrantyMonths INT DEFAULT 12, InvoiceFile VARCHAR(255), SignatureData TEXT,
        EmployeeName VARCHAR(255), EmployeeID VARCHAR(255), Designation VARCHAR(255), Department VARCHAR(255), Email VARCHAR(255),
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
    cur.execute("""CREATE TABLE IF NOT EXISTS History (
        id INT AUTO_INCREMENT PRIMARY KEY, asset_id VARCHAR(40), ts DATETIME, user VARCHAR(80),
        field VARCHAR(80), old_val TEXT, new_val TEXT,
        INDEX idx_hist (asset_id)
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
    cur.execute("""CREATE TABLE IF NOT EXISTS Users (
        username VARCHAR(50) PRIMARY KEY,
        password VARCHAR(100),
        role VARCHAR(20),
        display VARCHAR(80),
        email VARCHAR(160)
    )""")
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
        app_name VARCHAR(60) DEFAULT 'Sha The IT Guy',
        logo_text VARCHAR(40) DEFAULT 'Sha',
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
        for col, typ in [("app_name","VARCHAR(60) DEFAULT 'Sha The IT Guy'"),("logo_text","VARCHAR(40) DEFAULT 'Sha'"),("matrix_on","BOOLEAN DEFAULT 1")]:
            try: cur.execute(f"ALTER TABLE Settings ADD COLUMN {col} {typ}")
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
    if not os.path.exists(os.path.join(BASE, "logo.png")):
        open(os.path.join(BASE, "logo.png"), "wb").close()  # placeholder
    cur.execute("SELECT COUNT(*) AS n FROM Users")
    if cur.fetchone()["n"] == 0:
        cur.execute("INSERT INTO Users (username, password, role, display, email) VALUES (%s,%s,%s,%s,%s)",
                    (ADMIN_USER, hash_pw(ADMIN_PASS), ROLE_ADMIN, "Administrator", ""))
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
    cur.execute("SELECT username, password, role, display FROM Users WHERE username=%s", [u])
    row = cur.fetchone(); c.close()
    if row and verify_pw(p, row["password"]):
        session["user"] = row["username"]; session["role"] = row["role"]; session["display"] = row["display"]
        session.permanent = True
        return jsonify({"ok": True, "role": row["role"]})
    return jsonify({"ok": False, "error": "Invalid credentials"}), 401

@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear(); return jsonify({"ok": True})

@app.route("/api/me")
def me():
    if not session.get("user"):
        return jsonify({"user": None})
    c = conn(); cur = c.cursor()
    cur.execute("SELECT display, email, avatar, api_key, last_login FROM Users WHERE username=%s", [session["user"]])
    row = cur.fetchone() or {}
    cur.execute("SELECT theme, ldap_server, ldap_domain, ldap_bind_user, ldap_base_dn, theme_preset, bg_type, bg, comp_bg, radius, font, accent, accent2, language, currency, region, matrix_on, app_name, logo_text, logo FROM Settings WHERE id=1")
    s = cur.fetchone() or {"theme":"dark"}
    c.close()
    return jsonify({"user": session["user"], "role": session["role"],
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
                    "app_name": s.get("app_name", "Sha The IT Guy"), "logo_text": s.get("logo_text", "Sha"),
                    "logo": "/logo.png",
                    "ldap_server": s.get("ldap_server", ""), "ldap_domain": s.get("ldap_domain", ""),
                    "ldap_bind_user": s.get("ldap_bind_user", ""), "ldap_base_dn": s.get("ldap_base_dn", "")})

def auth_required(role=None):
    from functools import wraps
    def deco(f):
        @wraps(f)
        def wrap(*a, **k):
            if not session.get("user"):
                return jsonify({"error": "unauthorized"}), 401
            if role and session.get("role") not in (role if isinstance(role, list) else [role]):
                return jsonify({"error": "forbidden"}), 403
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
@auth_required()
def list_employees():
    c = conn(); cur = c.cursor()
    cur.execute("SELECT * FROM Employees ORDER BY EmployeeName")
    rows = cur.fetchall(); c.close()
    return jsonify(rows)

@app.route("/api/employees", methods=["POST"])
@auth_required([ROLE_ADMIN, ROLE_EDIT])
def create_employee():
    import uuid
    data = request.get_json(force=True) or {}
    emp = {
        "_id": uuid.uuid4().hex,
        "EmployeeID": data.get("EmployeeID") or "",
        "EmpCode": data.get("EmpCode") or "",
        "EmployeeName": data.get("EmployeeName") or "",
        "Designation": data.get("Designation") or "",
        "Department": data.get("Department") or "",
        "Email": data.get("Email") or "",
        "source": "manual"
    }
    c = conn(); cur = c.cursor()
    cur.execute("""INSERT INTO Employees (_id, EmployeeID, EmpCode, EmployeeName, Designation, Department, Email, source)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (emp["_id"], emp["EmployeeID"], emp["EmpCode"], emp["EmployeeName"], emp["Designation"], emp["Department"], emp["Email"], emp["source"]))
    c.commit(); c.close()
    return jsonify(emp)

@app.route("/api/employees/<e_id>", methods=["PUT"])
@auth_required([ROLE_ADMIN, ROLE_EDIT])
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
@auth_required([ROLE_ADMIN, ROLE_EDIT])
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
@auth_required([ROLE_ADMIN, ROLE_EDIT])
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
        cur.execute("""INSERT INTO Employees (_id, EmployeeID, EmployeeName, Designation, Department, Email, source)
                       VALUES (%s,%s,%s,%s,%s,%s,'ldap')""",
                    (emp_id, item.get("EmployeeID",""), item.get("EmployeeName",""), item.get("Designation",""),
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
            cur.execute("""INSERT INTO Employees (_id, EmployeeID, EmployeeName, Designation, Department, Email, source)
                           VALUES (%s,%s,%s,%s,%s,%s,'ldap')""",
                        (uuid.uuid4().hex, sam, name, desig, dept, email))
            added += 1
    try:
        lc.unbind()
    except Exception:
        pass
    c.commit(); c.close()
    return {"added": added, "updated": updated, "total": len(seen)}

@app.route("/api/employees/ldap-sync", methods=["POST"])
@auth_required([ROLE_ADMIN, ROLE_EDIT])
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
@auth_required()
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
        sql += " ORDER BY Name"
    cur.execute(sql, params); rows = cur.fetchall(); c.close()
    return jsonify([row_to_dict(r) for r in rows])

@app.route("/api/assets", methods=["POST"])
@auth_required([ROLE_ADMIN, ROLE_EDIT])
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
    vals = [a_id] + [coerce_val(col, data.get(col)) for col in COLUMNS] + [datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
    cols = "_id, " + ", ".join(f"`{col}`" for col in COLUMNS) + ", created_at"
    ph = ", ".join(["%s"] * (len(COLUMNS) + 2))
    cur.execute(f"INSERT INTO Assets ({cols}) VALUES ({ph})", vals); c.commit(); c.close()
    send_notification("IT Guy: New asset added", f"Asset '{data.get('Name','?')}' (S/N {data.get('Serial','?')}) was added by {session.get('user')}.")
    return jsonify({"ok": True, "_id": a_id})

@app.route("/api/assets/<a_id>", methods=["GET"])
@auth_required()
def get_asset(a_id):
    c = conn(); cur = c.cursor()
    cur.execute("SELECT * FROM Assets WHERE _id=%s AND is_deleted=0", [a_id])
    row = cur.fetchone(); c.close()
    if not row: return jsonify({"error": "not found"}), 404
    return jsonify(row_to_dict(row))


@app.route("/api/assets/<a_id>", methods=["PUT"])
@auth_required([ROLE_ADMIN, ROLE_EDIT])
def update_asset(a_id):
    data = request.get_json(force=True)
    c = conn(); cur = c.cursor()
    # capture old values for history
    cur.execute("SELECT _id, " + ", ".join(f"`{col}`" for col in COLUMNS) + " FROM Assets WHERE _id=%s AND is_deleted=0", [a_id])
    old = cur.fetchone()
    if not old:
        c.close(); return jsonify({"error": "not found"}), 404
    old = row_to_dict(old)
    sets = ", ".join(f"`{col}`=%s" for col in COLUMNS)
    vals = [coerce_val(col, data.get(col)) for col in COLUMNS] + [a_id]
    cur.execute(f"UPDATE Assets SET {sets} WHERE _id=%s", vals)
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
    return jsonify({"ok": True})

@app.route("/api/assets/<a_id>", methods=["DELETE"])
@auth_required([ROLE_ADMIN, ROLE_EDIT])
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
@auth_required()
def asset_history(a_id):
    c = conn(); cur = c.cursor()
    cur.execute("SELECT ts, user, field, old_val, new_val FROM History WHERE asset_id=%s ORDER BY ts DESC", [a_id])
    rows = cur.fetchall(); c.close()
    return jsonify([{"ts": str(r["ts"]), "user": r["user"], "field": r["field"],
                    "old_val": r["old_val"], "new_val": r["new_val"]} for r in rows])

@app.route("/api/assets/<a_id>/restore", methods=["POST"])
@auth_required([ROLE_ADMIN, ROLE_EDIT])
def restore_asset(a_id):
    c = conn(); cur = c.cursor()
    cur.execute("UPDATE Assets SET is_deleted=0 WHERE _id=%s", [a_id]); c.commit(); c.close()
    return jsonify({"ok": True})

@app.route("/api/assets/trash")
@auth_required([ROLE_ADMIN, ROLE_EDIT])
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
@auth_required([ROLE_ADMIN, ROLE_EDIT])
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
@auth_required([ROLE_ADMIN, ROLE_EDIT])
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
@auth_required([ROLE_ADMIN, ROLE_EDIT])
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

@app.route("/api/export")
@auth_required()
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

# ---------- users (admin only) ----------
@app.route("/api/users")
@auth_required([ROLE_ADMIN])
def list_users():
    c = conn(); cur = c.cursor()
    cur.execute("SELECT username, role, display, email FROM Users ORDER BY role, username"); rows = cur.fetchall(); c.close()
    return jsonify([{"username": r["username"], "role": r["role"], "display": r["display"], "email": r.get("email", "")} for r in rows])

@app.route("/api/users", methods=["POST"])
@auth_required([ROLE_ADMIN])
def create_user():
    d = request.get_json(force=True)
    u = (d.get("username") or "").strip(); pw = d.get("password", ""); role = d.get("role", ROLE_VIEW); disp = d.get("display", "") or u; em = d.get("email", "").strip()
    if not u or not pw: return jsonify({"error": "username and password required"}), 400
    if role not in ROLES: return jsonify({"error": "invalid role"}), 400
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
    if "role" in d and d["role"] in ROLES: sets.append("role=%s"); vals.append(d["role"])
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
        return jsonify({"ok": False, "msg": str(e)}), 400

@app.route("/api/test-ldap", methods=["POST"])
@auth_required([ROLE_ADMIN])
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

# ---------- settings (admin) ----------
@app.route("/api/settings", methods=["GET", "PUT"])
@auth_required([ROLE_ADMIN])
def settings():
    c = conn(); cur = c.cursor()
    if request.method == "PUT":
        # accept JSON or multipart FormData (branding uses FormData)
        if request.content_type and "multipart/form-data" in request.content_type:
            d = request.form.to_dict()
            logo = request.files.get("logo") if "logo" in request.files else None
        else:
            d = request.get_json(force=True) or {}
            logo = None
        # load current row so partial saves (e.g. branding only) don't reset other fields
        cur.execute("SELECT theme, smtp_host, smtp_port, smtp_user, smtp_pass, smtp_from, notify_new, notify_delete, app_name, logo_text, matrix_on, ldap_server, ldap_domain, ldap_bind_user, ldap_bind_pass, ldap_base_dn, qr_size, qr_fields, label_size, label_logo, theme_preset, bg_type, bg, comp_bg, radius, font, accent, accent2, language, currency, region, portal_token, sla_low, sla_normal, sla_high, sla_urgent, sla_breach_notify, auto_assign_roundrobin, notify_on_create, notify_on_resolve, notify_on_reply FROM Settings WHERE id=1")
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
                     (d.get("app_name", cur0.get("app_name","Sha The IT Guy") )[:60]), (d.get("logo_text", cur0.get("logo_text","Sha"))[:40]),
                     bool(d.get("matrix_on", cur0.get("matrix_on", True))),
                     (d.get("ldap_server", "") or "").strip(), (d.get("ldap_domain", "") or "").strip(),
                     (d.get("ldap_bind_user", "") or "").strip(), d.get("ldap_bind_pass", cur0.get("ldap_bind_pass","")),
                     (d.get("ldap_base_dn", "") or "").strip(),
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
        # persist DB connection config (points the app at a different MariaDB)
        if any(k in d for k in ("db_host", "db_port", "db_name", "db_user", "db_pass")):
            save_db_config(d.get("db_host", DB_HOST), d.get("db_port", DB_PORT),
                           d.get("db_name", DB_NAME), d.get("db_user", DB_USER),
                           d.get("db_pass", DB_PASS))
        if logo:
            try:
                data = logo.read()
                cur.execute("UPDATE Settings SET logo=%s WHERE id=1", (data,))
                with open(os.path.join(BASE, "logo.png"), "wb") as fp:
                    fp.write(data)
            except Exception:
                pass
        elif str(d.get("remove_logo", "")).lower() in ("1", "true"):
            cur.execute("UPDATE Settings SET logo=NULL WHERE id=1")
            try:
                open(os.path.join(BASE, "logo.png"), "wb").close()
            except Exception:
                pass
        c.commit(); c.close()
        return jsonify({"ok": True})
    cur.execute("SELECT * FROM Settings WHERE id=1"); s = cur.fetchone(); c.close()
    s = s or {}
    return jsonify({k: s.get(k) for k in ["theme","smtp_host","smtp_port","smtp_user","smtp_from",
                                          "notify_new","notify_delete","app_name","logo_text","matrix_on",
                                          "ldap_server","ldap_domain","ldap_bind_user","ldap_bind_pass","ldap_base_dn",
                                          "qr_size","qr_fields","label_size","label_logo",
                                          "theme_preset","bg_type","bg","comp_bg","radius","font","accent","accent2",
                                          "language","currency","region","portal_token",
                                          "sla_low","sla_normal","sla_high","sla_urgent","sla_breach_notify",
                                          "auto_assign_roundrobin","notify_on_create","notify_on_resolve","notify_on_reply"]} | {
                "db_host": DB_HOST, "db_port": DB_PORT, "db_name": DB_NAME,
                "db_user": DB_USER, "db_pass": DB_PASS})

# ---------- contracts / locations (GLPI-style) ----------
@app.route("/api/contracts", methods=["GET","POST","PUT","DELETE"])
@auth_required([ROLE_ADMIN, ROLE_EDIT])
def contracts_api():
    c = conn(); cur = c.cursor()
    if request.method == "GET":
        cur.execute("SELECT * FROM Contracts ORDER BY end_date"); rows = cur.fetchall(); c.close()
        return jsonify([dict(r) for r in rows])
    if request.method == "POST":
        d = request.get_json(force=True)
        cur.execute("INSERT INTO Contracts (name, vendor, type, start_date, end_date, cost, asset_id, note) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (d.get("name",""), d.get("vendor",""), d.get("type",""), d.get("start_date",""), d.get("end_date",""),
                     float(d.get("cost") or 0), d.get("asset_id") or None, d.get("note","")))
        c.commit(); c.close(); return jsonify({"ok": True})
    if request.method == "PUT":
        d = request.get_json(force=True); cid = d.get("id")
        cur.execute("UPDATE Contracts SET name=%s, vendor=%s, type=%s, start_date=%s, end_date=%s, cost=%s, asset_id=%s, note=%s WHERE id=%s",
                    (d.get("name",""), d.get("vendor",""), d.get("type",""), d.get("start_date",""), d.get("end_date",""),
                     float(d.get("cost") or 0), d.get("asset_id") or None, d.get("note",""), cid))
        c.commit(); c.close(); return jsonify({"ok": True})
    cid = (request.get_json(force=True) or {}).get("id")
    cur.execute("DELETE FROM Contracts WHERE id=%s", [cid]); c.commit(); c.close(); return jsonify({"ok": True})

@app.route("/api/locations", methods=["GET","POST","DELETE"])
@auth_required([ROLE_ADMIN, ROLE_EDIT])
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
        bn = settings.get("app_name") or "Sha The IT Guy"
        subj = f"{bn}: Ticket {ticket['code']} Resolved"
        body = (f"Your ticket has been resolved.\n\nCode: {ticket['code']}\nSubject: {ticket.get('subject','')}\nStatus: {ticket.get('status','')}\n\nIf you need further assistance, reply to this email or submit a new ticket.")
        msg = EmailMessage(); msg["Subject"] = subj
        msg["From"] = settings.get("smtp_from") or settings.get("smtp_user")
        msg["To"] = ticket["requester_email"]; msg.set_content(body)
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
        bn = settings.get("app_name") or "Sha The IT Guy"
        subj = f"{bn}: Reply on Ticket {ticket['code']}"
        body = (f"Your ticket received a reply.\n\nCode: {ticket['code']}\nSubject: {ticket.get('subject','')}\nReply from: {reply_author}\n\n{reply_body[:500]}\n\nLogin to view full thread.")
        msg = EmailMessage(); msg["Subject"] = subj
        msg["From"] = settings.get("smtp_from") or settings.get("smtp_user")
        msg["To"] = ticket["requester_email"]; msg.set_content(body)
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
@auth_required()
def tickets_api():
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
                (code, d.get("subject","").strip(), d.get("description",""), priority,
                 d.get("requester",""), d.get("requester_email",""), assignee, d.get("asset_id") or None,
                 due_date, sla_hours, category, d.get("source","Web"), session.get("user","?")))
    tid = cur.lastrowid
    c.commit(); c.close()
    # notify after commit
    ticket = {"id": tid, "code": code, "subject": d.get("subject",""), "priority": priority, "requester": d.get("requester",""), "requester_email": d.get("requester_email",""), "category": category}
    try: notify_ticket_created(ticket)
    except Exception as e: print("notify created error:", e)
    return jsonify({"ok": True, "id": tid, "code": code})

@app.route("/api/portal/tickets", methods=["POST"])
def portal_create_ticket():
    """Public (no auth) ticket/request intake from the portal invite link."""
    d = request.get_json(force=True) or {}
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
                 (d.get("requester") or "").strip(), (d.get("requester_email") or "").strip(),
                 assignee, due_date, sla_hours, category))
    tid = cur.lastrowid
    c.commit(); c.close()
    ticket = {"id": tid, "code": code, "subject": subject, "priority": priority, "requester": d.get("requester",""), "requester_email": d.get("requester_email",""), "category": category}
    try: notify_ticket_created(ticket)
    except Exception as e: print("notify created error:", e)
    return jsonify({"ok": True, "code": code, "id": tid})

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
    return jsonify({"url": url, "token": s.get("portal_token") or "", "app_name": s.get("app_name") or "Sha The IT Guy"})

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
    reps = cur.fetchall(); c.close()
    return jsonify({"ticket": dict(t), "replies": [dict(r) for r in reps]})

@app.route("/api/tickets/<int:ticket_id>", methods=["GET","PUT","DELETE"])
@auth_required()
def ticket_detail(ticket_id):
    c = conn(); cur = c.cursor()
    if request.method == "GET":
        cur.execute("SELECT * FROM Tickets WHERE id=%s", [ticket_id]); t = cur.fetchone()
        if not t: c.close(); return jsonify({"error":"not found"}), 404
        cur.execute("SELECT * FROM TicketReplies WHERE ticket_id=%s ORDER BY created_at", [ticket_id]); reps = cur.fetchall()
        c.close(); return jsonify({"ticket": dict(t), "replies": [dict(r) for r in reps]})
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
        c.commit(); c.close()
        # notify on assignment change
        new_assignee = d.get("assignee")
        if new_assignee and new_assignee != (before.get("assignee") or ""):
            try: notify_ticket_assigned(dict(before), new_assignee)
            except Exception as e: print("assign notify call error:", e)
        # notify on resolve
        if d.get("status") in ("Resolved","Closed") and before.get("status") not in ("Resolved","Closed"):
            try: notify_ticket_resolved(dict(before))
            except Exception as e: print("resolve notify error:", e)
        return jsonify({"ok": True})
    cur.execute("DELETE FROM Tickets WHERE id=%s", [ticket_id])
    cur.execute("DELETE FROM TicketReplies WHERE ticket_id=%s", [ticket_id])
    c.commit(); c.close(); return jsonify({"ok": True})

@app.route("/api/tickets/<int:ticket_id>/reply", methods=["POST"])
@auth_required()
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
@auth_required([ROLE_ADMIN])
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
    cur.execute("SELECT app_name, logo_text, matrix_on, theme, theme_preset, bg_type, bg, comp_bg, radius, font, accent, accent2, language, currency FROM Settings WHERE id=1"); s = cur.fetchone(); c.close()
    s = s or {}
    return jsonify({"app_name": s.get("app_name", "Sha The IT Guy"), "logo_text": s.get("logo_text", "Sha"),
                    "matrix_on": bool(s.get("matrix_on", 1)), "logo": "/logo.png",
                    "theme": s.get("theme", "dark"), "theme_preset": s.get("theme_preset", "deepdark"),
                    "bg_type": s.get("bg_type", "solid"), "bg": s.get("bg", "#0a0d13"),
                    "comp_bg": s.get("comp_bg", "#121826"), "radius": s.get("radius", 12),
                    "font": s.get("font", "Rajdhani"), "accent": s.get("accent", "#ff3b30"),
                    "accent2": s.get("accent2", "#c0392b"), "language": s.get("language", "en"),
                    "currency": s.get("currency", "AED")})

@app.route("/api/logo", methods=["POST"])
@auth_required([ROLE_ADMIN])
def upload_logo():
    if "file" not in request.files:
        return jsonify({"error": "no file"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "no file"}), 400
    data = f.read()
    if len(data) > 500 * 1024:
        return jsonify({"error": "logo too large (max 500KB)"}), 400
    with open(os.path.join(BASE, "logo.png"), "wb") as fp:
        fp.write(data)
    return jsonify({"ok": True, "logo": "/logo.png"})

@app.route("/logo.png")
def logo_file():
    p = os.path.join(BASE, "logo.png")
    if os.path.exists(p) and os.path.getsize(p) > 0:
        return send_from_directory(BASE, "logo.png")
    # transparent 1px fallback so <img> doesn't break
    from flask import Response as _R
    return _R(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xcf\xc0\xf0\x1f\x00\x05\x05\x02\x00\x9d\xfd\xa4\x1e\x00\x00\x00\x00IEND\xaeB`\x82",
                    mimetype="image/png")

# ---------- email notifications ----------
def brand_name():
    try:
        c = conn(); cur = c.cursor()
        cur.execute("SELECT app_name FROM Settings WHERE id=1"); r = cur.fetchone(); c.close()
        return (r.get("app_name") or "Sha The IT Guy") if r else "Sha The IT Guy"
    except Exception:
        return "Sha The IT Guy"
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
        bn = s.get("app_name") or "Sha The IT Guy"
        subj = subject if subject.startswith(bn) else f"{bn}: {subject}" if not subject.startswith("IT Guy") else subject.replace("IT Guy", bn, 1)
        msg = EmailMessage(); msg["Subject"] = subj; msg["From"] = s.get("smtp_from") or s.get("smtp_user")
        msg["To"] = ", ".join(emails); msg.set_content(body)
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
    bn = s.get("app_name") or "Sha The IT Guy"
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
                f"Login to {s.get('app_name') or 'Sha The IT Guy'} to update status and reply.\n")
        msg = EmailMessage(); msg["Subject"] = subj
        msg["From"] = s.get("smtp_from") or s.get("smtp_user")
        msg["To"] = ", ".join(recipients); msg.set_content(body)
        with smtplib.SMTP(s["smtp_host"], int(s.get("smtp_port", 587) or 587), timeout=10) as sv:
            if s.get("smtp_user"): sv.starttls(); sv.login(s["smtp_user"], s.get("smtp_pass", ""))
            sv.send_message(msg)
        return True
    except Exception as e:
        print("assign notify error:", e); return False

@app.route("/api/settings/smtp-test", methods=["POST"])
@auth_required([ROLE_ADMIN])
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
        msg = EmailMessage()
        msg["Subject"] = "IT Guy Assets Manager · SMTP check ✅"
        msg["From"] = frm
        msg["To"] = to
        msg.set_content(
            "Yo — this is your SMTP test email from IT Guy Assets Manager.\n\n"
            "If it landed in your inbox, your setup is locked in and ready to send "
            "real notifications. No cap. \U0001F680\n\n"
            "Nothing else to do here — you're good to go."
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
@auth_required([ROLE_ADMIN, ROLE_EDIT])
def checkout_asset(a_id):
    d = request.get_json(force=True)
    user = (d.get("username") or "").strip()
    if not user: return jsonify({"error": "username required"}), 400
    expected = (d.get("expected") or "").strip()
    note = (d.get("note") or "").strip()
    c = conn(); cur = c.cursor()
    cur.execute("SELECT _id, Name FROM Assets WHERE _id=%s", [a_id]); a = cur.fetchone()
    if not a: c.close(); return jsonify({"error": "asset not found"}), 404
    cur.execute("UPDATE Assets SET Status='Checked-Out', ReceivedBy=%s WHERE _id=%s", (user, a_id))
    cur.execute("INSERT INTO Checkouts (asset_id, username, checkout_date, expected_checkin, note) VALUES (%s,%s,%s,%s,%s)",
                (a_id, user, nowstr(), expected, note))
    c.commit(); c.close()
    audit(session.get("user"), "CHECKOUT", a_id, f"{a['Name']} -> {user}" + (f" (due {expected})" if expected else ""))
    send_notification("IT Guy: Asset checked out", f"'{a['Name']}' was checked out to {user} by {session.get('user')}.")
    return jsonify({"ok": True})

@app.route("/api/assets/<a_id>/checkin", methods=["POST"])
@auth_required([ROLE_ADMIN, ROLE_EDIT])
def checkin_asset(a_id):
    c = conn(); cur = c.cursor()
    cur.execute("SELECT _id, Name FROM Assets WHERE _id=%s", [a_id]); a = cur.fetchone()
    if not a: c.close(); return jsonify({"error": "asset not found"}), 404
    cur.execute("SELECT id FROM Checkouts WHERE asset_id=%s AND checkin_date IS NULL ORDER BY id DESC LIMIT 1", [a_id])
    co = cur.fetchone()
    if co:
        cur.execute("UPDATE Checkouts SET checkin_date=%s WHERE id=%s", (nowstr(), co["id"]))
    cur.execute("UPDATE Assets SET Status='Available', ReceivedBy='' WHERE _id=%s", [a_id])
    c.commit(); c.close()
    audit(session.get("user"), "CHECKIN", a_id, f"{a['Name']} returned")
    return jsonify({"ok": True})

# ---------- ITAM: maintenance ----------
@app.route("/api/assets/<a_id>/maintenance", methods=["GET", "POST", "DELETE"])
@auth_required([ROLE_ADMIN, ROLE_EDIT])
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
        cur.execute("SELECT Status FROM Assets WHERE _id=%s AND is_deleted=0", [a_id])
        arow = cur.fetchone()
        if arow and arow["Status"] != "Under-Maintenance":
            cur.execute("UPDATE Assets SET Status=%s WHERE _id=%s", ["Under-Maintenance", a_id])
            cur.execute("INSERT INTO History (asset_id, ts, user, field, old_val, new_val) VALUES (%s, NOW(), %s, %s, %s, %s)",
                        (a_id, session.get("user", "?"), "Status", arow["Status"], "Under-Maintenance"))
        c.commit(); c.close()
        audit(session.get("user"), "MAINTENANCE", a_id, f"{(d.get('mtype') or 'Repair')} cost {d.get('cost') or 0}")
        return jsonify({"ok": True})
    if request.method == "DELETE":
        mid = request.args.get("id")
        cur.execute("DELETE FROM Maintenance WHERE id=%s AND asset_id=%s", [mid, a_id]); c.commit(); c.close()
        return jsonify({"ok": True})

# ---------- audit log ----------
@app.route("/api/audit")
@auth_required([ROLE_ADMIN, ROLE_EDIT])
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
    c.close()
    return jsonify({"total": total, "checked_out": checked_out, "maintenance": maint,
                    "due_soon": due_soon, "warranty_expiring": warranty_exp,
                    "by_status": by_status, "by_type": by_type, "by_location": by_location})

# ---------- QR label ----------
@app.route("/api/assets/<a_id>/qr")
@auth_required()
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
        app_name = (srow.get("app_name") or "Sha The IT Guy") if srow else "Sha The IT Guy"
        logo_text = (srow.get("logo_text") or app_name) if srow else app_name
    except Exception:
        qr_size, label_size, show_logo, app_name, logo_text = 160, "50.8x50.8", True, "Sha The IT Guy", "Sha"
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
    logo_uri = ""
    try:
        lc = conn(); lcur = lc.cursor()
        lcur.execute("SELECT logo FROM Settings WHERE id=1"); lr = lcur.fetchone(); lc.close()
        if lr and lr.get("logo"):
            import base64
            logo_uri = "data:image/png;base64," + base64.b64encode(lr["logo"]).decode("ascii")
    except Exception:
        logo_uri = ""
    if not logo_uri:
        try:
            with open(os.path.join(BASE, "logo.png"), "rb") as fp:
                import base64
                logo_uri = "data:image/png;base64," + base64.b64encode(fp.read()).decode("ascii")
        except Exception:
            logo_uri = ""
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
        app_name = (srow.get("app_name") or "Sha The IT Guy") if srow else "Sha The IT Guy"
    except Exception:
        qr_size, label_size, show_logo, app_name = 160, "50.8x50.8", True, "Sha The IT Guy"
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
    logo_uri = ""
    try:
        lc = conn(); lcur = lc.cursor()
        lcur.execute("SELECT logo FROM Settings WHERE id=1"); lr = lcur.fetchone(); lc.close()
        if lr and lr.get("logo"):
            import base64
            logo_uri = "data:image/png;base64," + base64.b64encode(lr["logo"]).decode("ascii")
    except Exception:
        logo_uri = ""
    if not logo_uri:
        try:
            with open(os.path.join(BASE, "logo.png"), "rb") as fp:
                import base64
                logo_uri = "data:image/png;base64," + base64.b64encode(fp.read()).decode("ascii")
        except Exception:
            logo_uri = ""
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
    cur.execute("SELECT _id, " + ", ".join(f"`{col}`" for col in COLUMNS) + ", InvoiceFile FROM Assets WHERE _id=%s", [a_id])
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
        scur.execute("SELECT app_name, logo_text, org_contact FROM Settings WHERE id=1")
        srow = scur.fetchone(); sc.close()
        app_name = (srow.get("app_name") or "Sha The IT Guy") if srow else "Sha The IT Guy"
        logo_text = (srow.get("logo_text") or app_name) if srow else app_name
        org_contact = (srow.get("org_contact") or "") if srow else ""
    except Exception:
        app_name, logo_text, org_contact = "Sha The IT Guy", "Sha", ""
    # logo as base64
    logo_uri = ""
    try:
        lc = conn(); lcur = lc.cursor()
        lcur.execute("SELECT logo FROM Settings WHERE id=1"); lr = lcur.fetchone(); lc.close()
        if lr and lr.get("logo"):
            import base64
            logo_uri = "data:image/png;base64," + base64.b64encode(lr["logo"]).decode("ascii")
    except Exception:
        logo_uri = ""
    if not logo_uri:
        try:
            with open(os.path.join(BASE, "logo.png"), "rb") as fp:
                import base64
                logo_uri = "data:image/png;base64," + base64.b64encode(fp.read()).decode("ascii")
        except Exception:
            logo_uri = ""
    c.close()
    rows = [("Asset Name", asset.get("Name")), ("Asset ID", asset["_id"][:12]),
            ("Category", asset.get("Type")), ("Serial", asset.get("Serial")),
            ("Status", asset.get("Status")), ("Location", asset.get("Location")),
            ("Assigned To", emp_name or "—"), ("Department", asset.get("Department") or "—"),
            ("Designation", asset.get("Designation") or "—"), ("Email", asset.get("Email") or "—"),
            ("Signed By", asset.get("ReceivedBy") or "—"), ("Signed Date", asset.get("NotesReceived") or "—"),
            ("Warranty", str(asset.get("WarrantyMonths") or 12) + " mo"), ("Purchase", asset.get("PurchaseDate") or "—"),
            ("Note", asset.get("Note") or "—")]
    rows_html = "".join(f"<tr><td class='k'>{k}</td><td class='v'>{('' if v is None else v)}</td></tr>" for k,v in rows)
    logo_html = f'<img class=logo src="{logo_uri}" alt="">' if logo_uri else ""
    return f"""<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Asset {asset['Name']}</title>
<style>
 body{{font-family:'Segoe UI',Arial,sans-serif;margin:0;background:#0c111b;color:#e6f0f7}}
 .wrap{{max-width:560px;margin:0 auto;padding:20px}}
 .card{{background:#131b29;border:1px solid #233; border-radius:14px;padding:20px;box-shadow:0 8px 30px rgba(0,0,0,.4)}}
 .head{{display:flex;align-items:center;gap:12px;border-bottom:1px solid #2a3a4d;padding-bottom:12px;margin-bottom:14px}}
 .logo{{height:42px;width:auto;max-width:140px;object-fit:contain}}
 .brand{{font-weight:800;font-size:18px;letter-spacing:.5px;color:#5ad8ff;text-transform:uppercase}}
 .title{{font-size:22px;font-weight:700;margin:6px 0 14px}}
 table{{width:100%;border-collapse:collapse}}
 td{{padding:8px 6px;border-bottom:1px solid #1d2a3a;vertical-align:top}}
 .k{{color:#7f93a8;font-size:12px;width:42%}}
 .v{{font-size:14px}}
 .contact{{margin-top:16px;padding:12px 14px;background:#0e1622;border:1px solid #234;border-radius:10px;font-size:14px}}
 .contact b{{color:#5ad8ff}}
 .foot{{text-align:center;color:#5a6b7d;font-size:12px;margin-top:18px}}
 a.btn{{display:inline-block;margin-top:14px;padding:10px 16px;background:#5ad8ff;color:#04121a;border-radius:8px;text-decoration:none;font-weight:700;font-size:13px}}
</style></head><body><div class=wrap><div class=card>
 <div class=head>{logo_html}<span class=brand>{app_name}</span></div>
 <div class=title>{asset['Name']}</div>
 <table>{rows_html}</table>
 <div class=contact>📞 Organization Contact: <b>{org_contact or '—'}</b></div>
 <a class=btn href="{base}label/{asset['_id']}">🖨 Open Printable Tag</a>
 <div class=foot>Scanned from IT Guy - The Assets Manager • {base}</div>
</div></div></body></html>"""

# ---------- invoice attachment ----------
ALLOWED_EXT = {"pdf", "png", "jpg", "jpeg", "gif", "webp", "bmp", "tif", "tiff"}
import mimetypes as _mtype

@app.route("/api/assets/<a_id>/invoice", methods=["POST"])
@auth_required([ROLE_ADMIN, ROLE_EDIT])
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
@auth_required([ROLE_ADMIN, ROLE_EDIT])
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
@auth_required([ROLE_ADMIN, ROLE_EDIT])
def get_sign_link(a_id):
    c = conn(); cur = c.cursor()
    cur.execute("SELECT _id, Name FROM Assets WHERE _id=%s", [a_id]); a = cur.fetchone()
    if not a: c.close(); return jsonify({"error": "asset not found"}), 404
    tk = _sign_token({"asset_id":a_id, "name":a["Name"]}, exp_hours=7)
    c.close()
    return jsonify({"ok": True, "token": tk, "url": f"{request.host_url}sign?token={quote(tk)}"})

SIGNATURE_HTML = """<!doctype html><html lang="en"><head><meta charset=utf-8><meta name="viewport" content="width=device-width,initial-scale=1">
<title>IT Guy // Asset Acknowledgement</title>
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;900&family=Share+Tech+Mono&family=Rajdhani:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/style.css">
<style>
body{font-family:'Rajdhani',sans-serif;margin:0;padding:28px 16px;min-height:100vh;background:var(--bg);color:var(--txt);transition:background .25s,color .25s}
.sign-card{max-width:620px;margin:0 auto;background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:26px 26px 22px;box-shadow:0 10px 40px rgba(0,0,0,.35)}
.brand{font-family:'Orbitron';font-weight:900;font-size:26px;text-align:center;background:linear-gradient(90deg,var(--accent),var(--accent2));-webkit-background-clip:text;background-clip:text;color:transparent;margin:0 0 2px}
.sub{text-align:center;color:var(--muted);font-size:12px;letter-spacing:3px;margin-bottom:18px}
.asset-table{width:100%;border-collapse:collapse;margin:10px 0 18px;background:var(--surface2);border:1px solid var(--line);border-radius:var(--radius);overflow:hidden}
.asset-table td{padding:9px 14px;border-bottom:1px solid var(--line);font-size:14px}
.asset-table tr:last-child td{border-bottom:none}
.asset-table td:first-child{color:var(--muted);width:150px;font-size:12px;font-weight:600;letter-spacing:.3px;text-transform:uppercase}
.asset-table td:last-child{color:var(--txt);font-weight:600;word-break:break-word}
.sig-label{color:var(--muted);font-size:13px;margin-bottom:6px;display:block}
#sigCanvas{width:100%;max-width:480px;height:160px;border-radius:var(--radius);background:var(--surface2);border:2px solid var(--line);cursor:crosshair;display:none;touch-action:none}
#sigPlaceholder{width:100%;max-width:480px;height:160px;display:flex;align-items:center;justify-content:center;color:var(--muted);font-size:14px;border:2px dashed var(--line);border-radius:var(--radius);background:var(--surface2);cursor:pointer}
#sigPlaceholder.hidden{display:none}
.btnrow{display:flex;gap:10px;flex-wrap:wrap;margin-top:8px}
.btnrow .btn{flex:1;min-width:140px}
#result{margin-top:16px;font-size:14px;min-height:24px}
.ok{color:var(--grn)}.err{color:var(--red);white-space:pre-wrap}
.center{text-align:center;margin-top:40px;color:var(--muted)}
</style></head><body>
<div class="sign-card">
  <div class="brand" id="brand">IT Guy</div>
  <div class="sub" id="sub">// ASSET ACKNOWLEDGEMENT</div>
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
    <button class="btn ghost" id="printSign">🖨 PRINT</button>
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
  const w = canvas.offsetWidth||480, h = canvas.offsetHeight||160;
  canvas.width = w; canvas.height = h;
  ctx = canvas.getContext('2d');
  ctx.lineWidth = 2; ctx.lineCap='round';
  ctx.strokeStyle = accentColor();
  ctx.fillStyle = getComputedStyle(canvas).backgroundColor||'#121826';
  ctx.fillRect(0,0,w,h);
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
function showCanvas(){ initCanvas(); placeholder.classList.add('hidden'); canvas.style.display='block'; canvas.focus(); }
placeholder.addEventListener('click',()=>{showCanvas();});
canvas.addEventListener('mousedown',startDraw);
canvas.addEventListener('mousemove',draw);
canvas.addEventListener('mouseup',stopDraw);
canvas.addEventListener('mouseleave',stopDraw);
canvas.addEventListener('touchstart',startDraw,{passive:false});
canvas.addEventListener('touchmove',draw,{passive:false});
canvas.addEventListener('touchend',stopDraw,{passive:false});
function clearSig(){ if(!ctx) return; ctx.clearRect(0,0,canvas.width,canvas.height); hasSig=false; const c=document.getElementById('clearSign'); if(c)c.style.display='none'; }
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
  document.getElementById('assetCard').innerHTML=
    '<table class=asset-table>'+
    '<tr><td>Name</td><td>'+esc(a.Name)+'</td></tr>'+
    '<tr><td>Type</td><td>'+esc(a.Type)+'</td></tr>'+
    '<tr><td>Serial</td><td>'+esc(a.Serial)+'</td></tr>'+
    '<tr><td>Status</td><td>'+esc(a.Status)+'</td></tr>'+
    '<tr><td>Location</td><td>'+esc(a.Location)+'</td></tr>'+
    '<tr><td>Notes</td><td>'+esc(a.Notes||'—')+'</td></tr>'+
    '<tr><td>Received By</td><td>'+esc(receivedBy||'Not yet received')+'</td></tr>'+
    '<tr><td>Received Details</td><td>'+esc(notesReceived||'Not yet received')+'</td></tr>'+
    '</table>';
}
document.getElementById('clearSign').addEventListener('click',()=>{clearSig();});
document.getElementById('printSign').addEventListener('click',()=>{window.print();});
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
  if(j.ok){res.className='ok';res.innerHTML='✅ <b>ACKNOWLEDGED</b> — Thank you!';document.querySelector('.btn').disabled=true;document.getElementById('signer').disabled=true;placeholder.classList.add('hidden');clearSig();const v=document.getElementById('viewSign');if(v){v.style.display='block';v.onclick=()=>{const w=window.open('','_blank');w.document.write('<img src="'+data+'" style="max-width:100%"/>');};}}
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
  const name=b.app_name||'Sha The IT Guy';
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
    cur.execute("SELECT _id AS id, Name, Type, Serial, Status, Location, Notes, ReceivedBy, NotesReceived, SignatureData FROM Assets WHERE _id=%s", [d["asset_id"]]); a = cur.fetchone(); c.close()
    if not a: return jsonify({"ok": False, "error": "asset not found"}), 404
    return jsonify({"ok": True, "asset": a})

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
    notesReceived = f"{name} | {ts}"
    sigData = (d.get("data") or "").strip()
    cur.execute("UPDATE Assets SET Status='Checked-Out', ReceivedBy=%s, Notes=CONCAT(IFNULL(Notes,''),'\\nAcknowledged by ',%s,' on ',NOW()), NotesReceived=%s, SignatureData=%s WHERE _id=%s",
                (receivedBy, name, notesReceived, sigData, aid))
    c.commit(); c.close()
    audit(session.get("user"), "ACKNOWLEDGE", aid, f"{name} acknowledged")
    return jsonify({"ok": True})

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
    if mac.lower() in ("ff-ff-ff-ff-ff-ff", "00-00-00-00-00-00"):
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


def _arp_devices():
    out = subprocess.run(["arp", "-a"], capture_output=True, text=True).stdout
    devs = {}
    for m in re.finditer(r"(\d+\.\d+\.\d+\.\d+)\s+([0-9a-f-]{17})\s+(\w+)", out, re.I):
        ip, mac, typ = m.group(1), m.group(2), m.group(3)
        if _is_real_host(ip, mac):
            devs[ip] = {"ip": ip, "mac": mac, "type": typ}
    return devs

def _ping_one(ip):
    try:
        r = subprocess.run(["ping", "-n", "1", "-w", "200", ip],
                           capture_output=True, text=True, timeout=2)
        # "Reply from" is localised on non-English Windows; TTL= is not, and a
        # 0 exit code alone is not reliable ("Destination host unreachable").
        out = r.stdout or ""
        alive = ("TTL=" in out.upper()) or ("Reply from" in out)
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
@auth_required([ROLE_ADMIN, ROLE_EDIT])
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
            if v is None: vals.append("NULL")
            elif isinstance(v, (int, float)): vals.append(str(v))
            else: vals.append("'" + str(v).replace("'", "''") + "'")
        out.append(f"REPLACE INTO `{table}` ({', '.join('`'+c+'`' for c in cols)}) VALUES ({', '.join(vals)});")
    return out

@app.route("/api/backup")
@auth_required([ROLE_ADMIN])
def backup():
    scope = (request.args.get("scope") or "all").lower()
    if scope not in ("config", "assets", "all"):
        scope = "all"
    c = conn(); cur = c.cursor()
    lines = [f"-- IT Guy backup | scope={scope} | {datetime.now().strftime('%Y-%m-%d %H:%M')}"]
    if scope in ("config", "all"):
        lines += ["-- == Settings ==", *_dump_table(cur, "Settings")]
        lines += ["-- == Users ==", *_dump_table(cur, "Users")]
    if scope in ("assets", "all"):
        lines += ["-- == Assets ==", *_dump_table(cur, "Assets")]
        lines += ["-- == Checkouts ==", *_dump_table(cur, "Checkouts")]
        lines += ["-- == Maintenance ==", *_dump_table(cur, "Maintenance")]
    if scope == "all":
        lines += ["-- == AuditLog ==", *_dump_table(cur, "AuditLog")]
    c.close()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"nexus_backup_{scope}_{stamp}.sql"
    fpath = os.path.join(BACKUP_DIR, fname)
    with open(fpath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    audit(session.get("user"), "BACKUP", "", f"scope={scope} file={fname}")
    return send_from_directory(BACKUP_DIR, fname, as_attachment=True,
                                mimetype="application/sql",
                                download_name=fname)

@app.route("/api/backups")
@auth_required([ROLE_ADMIN])
def list_backups():
    files = sorted([f for f in os.listdir(BACKUP_DIR) if f.endswith(".sql")], reverse=True)
    out = []
    for f in files:
        try:
            # filenames look like nexus_backup_<scope>_<YYYYMMDD>_<HHMMSS>.sql
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

BACKUP_FNAME_RE = re.compile(r"^nexus_backup_(all|config|assets)_\d{8}_\d{6}\.sql$")

@app.route("/api/backups/<fname>/download")
@auth_required([ROLE_ADMIN])
def download_backup(fname):
    if not BACKUP_FNAME_RE.match(fname):
        return jsonify({"error": "invalid filename"}), 400
    if not os.path.exists(os.path.join(BACKUP_DIR, fname)):
        return jsonify({"error": "not found"}), 404
    return send_from_directory(BACKUP_DIR, fname, as_attachment=True,
                                mimetype="application/sql", download_name=fname)

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

@app.route("/api/restore", methods=["POST"])
@auth_required([ROLE_ADMIN])
def restore():
    if "file" not in request.files:
        return jsonify({"error": "no file"}), 400
    f = request.files["file"]
    if not f.filename.endswith(".sql"):
        return jsonify({"error": "only .sql backup allowed"}), 400
    content = f.read().decode("utf-8", "replace")
    c = conn(); cur = c.cursor()
    applied = 0
    for stmt in content.split(";"):
        s = stmt.strip()
        if not s or s.startswith("--"): continue
        try:
            cur.execute(s); applied += 1
        except Exception as e:
            c.rollback(); c.close()
            return jsonify({"error": f"restore failed near: {s[:60]} -> {e}"}), 400
    c.commit(); c.close()
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


@app.route("/")
def index():
    if not session.get("user"):
        return send_from_directory(BASE, "login.html")
    return send_from_directory(BASE, "index.html")

@app.route("/<path:p>")
def static_files(p):
    if p in ("login.html", "index.html", "style.css", "app.js"):
        return send_from_directory(BASE, p)
    return jsonify({"error": "not found"}), 404

# ---------- LDAP auto-sync scheduler (background thread) ----------
import threading

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

if __name__ == "__main__":
    init_db()
    migrate_schema()
    start_ldap_scheduler()
    print("IT Guy - The Assets Manager (MariaDB) -> http://localhost:5000  (admin: %s)" % ADMIN_USER)
    app.run(host="0.0.0.0", port=5000, debug=False)
