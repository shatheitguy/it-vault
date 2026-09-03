# IT-Vault — Full Documentation

> GLPI-style IT Asset Management (ITAM) + osTicket-style ticketing, built on **Flask + MariaDB**.
> Local-only deployment (Windows host, no external hosting). Cyber/tech dark-slate UI with light theme.

---

## 1. Overview

IT-Vault is a single-tenant, self-hosted asset & ticket manager for IT teams (e.g. an sports club IT department). It manages:

- **Assets** (laptops, phones, CCTV, network gear) with full lifecycle, change history, QR labels, checkout/checkin, maintenance log, and digital acknowledgement (sign-off).
- **Employees** (manual or synced from Active Directory / LDAP).
- **Tickets** with threaded replies, priority, SLA, and asset linkage.
- **Contracts** (warranty/vendor) and **Locations** (site tree).
- **Trash** (soft-delete + restore).
- **System Settings** (language, currency, region, notifications, branding, theme).
- **Audit Log**, **Network Scan**, **Backup/Restore**, **Import/Export Excel**.

Stack: Python 3 (Flask), MariaDB 12.3, Jinja-free server-rendered HTML + vanilla JS SPA, openpyxl for Excel, ldap3 for AD sync, qrcode for labels.

---

## 2. Architecture

```
Browser (index.html SPA, app.js, style.css, login.html, /sign, /label/<id>, /asset/<id>)
        │  HTTP / JSON API + cookie session
        ▼
Flask app (app.py)  ── pymysql ──▶ MariaDB (db: itguy_assets)
        │
        ├─ openpyxl  (Excel import/export)
        ├─ ldap3     (AD/LDAP employee sync)
        └─ qrcode    (asset QR labels, rendered to PNG)

MariaDB 12.3 on 127.0.0.1:3306  (NOT a Windows service — start manually)
```

### Processes
- **Flask dev server** — `python app.py` → listens on `127.0.0.1:5000`. `debug=False`, so **no auto-reload**; after editing `app.py` you must kill the process on :5000 and relaunch.
- **MariaDB** — must be running before Flask starts, or DB calls fail with `pymysql 2003`.

---

## 3. Installation & First Run

### 3.1 Prerequisites
- Windows 10/11
- Python 3.11+ (the app uses the Hermes venv interpreter: `C:\Users\Sha\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe`)
- MariaDB 12.3 installed at `C:\Program Files\MariaDB 12.3`
- Python packages: `flask`, `pymysql`, `openpyxl`, `ldap3`, `qrcode`, `pillow`

> ⚠️ The Windows `python3` on PATH is the Microsoft Store shim and **exits code 23** — never use it. Use the venv interpreter above.

### 3.2 Start MariaDB
MariaDB is **not** installed as a Windows service. Start `mysqld` manually:

```
"C:\Program Files\MariaDB 12.3\bin\mysqld.exe" --datadir="C:\Program Files\MariaDB 12.3\data"
```

(Or whatever datadir your install uses.) Verify it is listening:

```
netstat -ano | findstr :3306
```

### 3.3 Create the database & user (one-time)
Using the MariaDB client:

```sql
CREATE DATABASE IF NOT EXISTS itguy_assets CHARACTER SET utf8mb4;
CREATE USER IF NOT EXISTS 'itguy'@'127.0.0.1' IDENTIFIED BY 'itguypass';
GRANT ALL PRIVILEGES ON itguy_assets.* TO 'itguy'@'127.0.0.1';
FLUSH PRIVILEGES;
```

### 3.4 Start the app
```bash
cd C:\Users\Sha\asset-manager
# kill any old process on :5000 first
for pid in $(netstat -ano | grep ":5000" | findstr LISTENING | awk '{print $5}'); do taskkill /PID $pid /F; done

# launch with the venv interpreter (background)
"C:\Users\Sha\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe" app.py
```

On first launch `init_db()` auto-creates all tables and seeds the admin user.

### 3.5 Default login
- **URL:** `http://127.0.0.1:5000`
- **Username:** `admin`
- **Password:** `admin123`

> Change these via env vars `ITGUY_ADMIN` / `ITGUY_ADMIN_PASS` or in code (`ADMIN_USER`/`ADMIN_PASS`).

---

## 4. Configuration

All config is read from environment variables (Docker-friendly), with local defaults:

| Env var | Default | Purpose |
|---|---|---|
| `DB_HOST` | `127.0.0.1` | MariaDB host |
| `DB_PORT` | `3306` | MariaDB port |
| `DB_NAME` | `itguy_assets` | Database name |
| `DB_USER` | `itguy` | DB user |
| `DB_PASS` | `itguypass` | DB password |
| `ITGUY_SECRET` | `itguy-local-secret-change-me` | Flask session signing secret |
| `ITGUY_ADMIN` | `admin` | Default admin username |
| `ITGUY_ADMIN_PASS` | `admin123` | Default admin password |

System-wide settings (persisted in the `Settings` table, row id=1) are editable from the **System** page: theme, app name, logo text, matrix animation, SMTP (notifications), language, currency, region, notification toggles, QR/label size, LDAP server credentials.

---

## 5. Data Model (MariaDB `itguy_assets`)

### Assets
| Column | Type | Notes |
|---|---|---|
| `_id` | VARCHAR(40) PK | UUID |
| `Name, Type, Serial, Location` | VARCHAR(255) | Core identity |
| `Status` | VARCHAR(255) | one of `STATUSES` (New, In Use, Available, Checked-Out, Under-Maintenance, Storage, Worn, Retired, Out of Service) |
| `ReceivedBy, NotesReceived, Notes, Note` | text | Handover / notes |
| `PurchaseDate` | VARCHAR(255) | |
| `WarrantyMonths` | INT | |
| `Price` | DECIMAL(12,2) | purchase price (currency-formatted) |
| `InvoiceFile` | VARCHAR(255) | uploaded invoice filename |
| `SignatureData` | TEXT | base64 PNG acknowledgement signature |
| `EmployeeName, EmployeeID, Designation, Department, Email` | VARCHAR(255) | assignment |
| `Manufacturer, Model` | VARCHAR(255) | GLPI-style reference |
| `is_deleted` | TINYINT | soft-delete flag (Trash) |

`COLUMNS` (table columns shown): `Name, Type, Serial, Location, Status, Manufacturer, Model, ReceivedBy, NotesReceived, Note, PurchaseDate, WarrantyMonths, Price, EmployeeID`.

### Other tables
- **Manufacturers** (`id`, `name` UNIQUE) · **Models** (`id`, `name`, `manufacturer_id`)
- **History** (`id`, `asset_id`, `ts`, `user`, `field`, `old_val`, `new_val`) — field-level change log
- **Contracts** (`id`, `name`, `vendor`, `type`, `start_date`, `end_date`, `cost`, `asset_id`, `note`)
- **Locations** (`id`, `name` UNIQUE, `parent_id`) — site tree
- **Tickets** (`id`, `code` UNIQUE, `subject`, `description`, `priority`, `status`, `requester`, `requester_email`, `assignee`, `asset_id`, `due_date`, `sla_hours`, `source`, `created_by`, `created_at`, `updated_at`, `closed_at`)
- **TicketReplies** (`id`, `ticket_id`, `author`, `author_role`, `body`, `created_at`)
- **Users** (`username` PK, `password` [hashed], `role`, `display`, `email`)
- **Employees** (`_id`, `EmployeeID`, `EmployeeName`, `Designation`, `Department`, `Email`, `source`)
- **Checkouts** (`id`, `asset_id`, `username`, `checkout_date`, `expected_checkin`, `checkin_date`, `note`)
- **Maintenance** (`id`, `asset_id`, `date`, `mtype`, `cost`, `note`, `by_user`)
- **AuditLog** (`id`, `ts`, `user`, `action`, `asset_id`, `detail`)
- **Settings** (row id=1): theme, smtp_*, notify_new, notify_delete, app_name, logo_text, matrix_on, ldap_*, qr_size, qr_fields, label_size, label_logo, org_contact

---

## 6. Authentication & Roles

Session-based (Flask `session` cookie, signed by `ITGUY_SECRET`).

| Role | Value | Permissions |
|---|---|---|
| **Admin** | `admin` | Everything: users, settings, LDAP, assets CRUD, tickets, contracts, etc. |
| **Read-Write** | `read-write` | Assets/contracts/tickets CRUD; **no** user/settings/LDAP management |
| **Read-Only** | `read-only` | View + change own password only |

Auth decorator: `@auth_required([ROLE_ADMIN, ROLE_EDIT])` etc. The sign-off page (`/sign`) is **public** (token-signed, no session needed).

### Endpoints
- `POST /api/login` `{username, password}` → sets session
- `POST /api/logout` → clears session, redirects to login
- `GET /api/me` → current user + applied theme/locale

---

## 7. UI / Navigation

Sidebar groups:
- **MAIN** — Dashboard (Assets), Add Asset
- **MANAGE** — Tickets, Contracts, Locations, Trash, Employees
- **CUSTOMIZE** — Customization (theme presets, background, accent, font, radius)
- **TOOLS** — Network Scan, Backup / Restore
- **ACCOUNT** — Settings (🧑 Profile modal), System (⚙️ System Settings page), Employees

Asset table features:
- Top horizontal scrollbar synced to the table; compact rows.
- **Columns** popover (▦) to toggle visible columns (persisted in `localStorage` key `nexus_cols`).
- Per-row actions (role-gated): **SIGN**, **EDIT**, **CHECKOUT**, **MAINT**, **QR**, **DEL** (and **PRINT**).
- Search box, filters, bulk actions.

### Asset row actions
| Button | What it does |
|---|---|
| **SIGN** | Opens the public acknowledgement flow (`/sign?token=...` link generated via `/api/assets/<id>/sign/link`); after sign-off the signature is stored in `SignatureData`. |
| **EDIT** | Opens asset modal (all `COLUMNS` + history tab). |
| **CHECKOUT** | Assigns to a user (creates `Checkouts` row, sets `Status='Checked-Out'`). |
| **MAINT** | Maintenance/Repair log modal — add/delete records (date, type, cost, note). |
| **QR** | Opens printable QR label (`/label/<id>`) ~50×19 mm with logo + LAN URL. |
| **PRINT** | Opens a printable asset detail card (all fields + signature image if signed). |
| **DEL** | Soft-delete → moves to Trash (`is_deleted=1`). |

---

## 8. Key Workflows

### 8.1 Add / Edit Asset
`POST /api/assets` or `PUT /api/assets/<id>`. Every field change is written to `History`. Invoice can be uploaded (`POST /api/assets/<id>/invoice`).

### 8.2 Checkout / Checkin
`POST /api/assets/<id>/checkout` (body: `username`, optional `expected_checkin`, `note`) → `Status='Checked-Out'`, `Checkouts` row opened.
`POST /api/assets/<id>/checkin` → closes the open checkout, `Status='Available'`.

### 8.3 Maintenance
`GET/POST/DELETE /api/assets/<id>/maintenance`. Records shown in the MAINT modal and the asset history.

### 8.4 Digital Sign-off (Acknowledgement)
1. Click **SIGN** on an asset → generates a token link `/api/assets/<id>/sign/link`.
2. Open `/sign?token=...` (can be sent to the recipient).
3. Recipient enters name, draws signature on canvas, clicks **SAVE**.
4. `POST /api/assets/sign/approve` stores the base64 signature in `SignatureData`, sets `Status='Checked-Out'`, logs `ACKNOWLEDGE` in AuditLog.
5. The signature now appears on the asset **PRINT** card and the `/sign` view.

> ⚠️ Sign tokens are **time-limited** (JWT `exp`). An expired token returns "invalid or expired token" and nothing is saved — generate a fresh link.

### 8.5 Tickets
`GET/POST /api/tickets`; `GET/PUT/DELETE /api/tickets/<id>`; `POST /api/tickets/<id>/reply` (threaded replies). Auto `code` like `TK-00012`. Priority + SLA hours + due date + assignee + linked asset.

### 8.6 Contracts & Locations
`GET/POST/PUT/DELETE /api/contracts`; `GET/POST/DELETE /api/locations` (parent_id for a site tree).

### 8.7 Trash / Restore
Soft-deleted assets appear at `GET /api/assets/trash`. `POST /api/assets/<id>/restore` un-deletes. `DELETE /api/assets/<id>` hard-deletes.

### 8.8 Import / Export
- `POST /api/import` (multipart `.xlsx/.xls/.csv`) → bulk insert/update assets.
- `GET /api/export` → downloads current assets as `.xlsx`.
Both accessible from the Assets area.

### 8.9 Network Scan
`GET /api/scan` → ARP/ping sweep of the LAN, returns discovered devices (used by the Scan modal; "CLEAN + RESCAN" re-runs).

### 8.10 Backup / Restore
- `GET /api/backup?scope=...` → downloads SQL dump (+ optional config).
- `GET /api/backups` → lists stored backups.
- `POST /api/restore` → restores from an uploaded dump.

### 8.11 LDAP / Active Directory Sync
Configured in **System** settings (LDAP server, domain, bind user, base DN). `POST /api/ldap/test` validates; `POST /api/employees/ldap-import` pulls users; a background scheduler auto-syncs every 30 min (`POST /api/employees/ldap-sync`).

---

## 9. Customization & Theming

Two theme layers:
1. **System Settings** (persisted in DB `Settings`): `theme` (dark/light), `app_name`, `logo_text`, `matrix_on`.
2. **Customization** page (sidebar): live theme presets, background type/color, accent + accent2, font, corner radius. Saved via `PUT /api/settings` (merged PATCH) and applied immediately.

Themes apply to:
- **Dashboard** (`/api/me` returns `theme`)
- **Login** (`/api/branding` returns theme + colors)
- **Sign page** (`/api/branding` + `applySignTheme()`)

> If a theme change "doesn't show," hard-refresh the page — old cached `app.js`/`style.css` may be served.

---

## 10. API Reference (summary)

| Method | Endpoint | Auth | Purpose |
|---|---|---|---|
| POST | `/api/login` | public | authenticate |
| POST | `/api/logout` | session | log out |
| GET | `/api/me` | session | current user + theme |
| GET/POST | `/api/assets` | rw+ | list / create assets |
| GET/PUT/DELETE | `/api/assets/<id>` | rw+ | read / update / delete |
| GET | `/api/assets/<id>/history` | rw+ | change history |
| GET | `/api/assets/trash` | rw+ | soft-deleted list |
| POST | `/api/assets/<id>/restore` | rw+ | un-delete |
| POST | `/api/assets/<id>/checkout` | rw+ | assign |
| POST | `/api/assets/<id>/checkin` | rw+ | return |
| GET/POST/DELETE | `/api/assets/<id>/maintenance` | rw+ | maintenance log |
| POST | `/api/assets/<id>/invoice` | rw+ | upload invoice |
| GET | `/api/assets/<id>/sign/link` | rw+ | generate sign token |
| GET | `/api/assets/sign/verify` | public | verify token (sign page) |
| POST | `/api/assets/sign/approve` | public | save signature |
| GET | `/api/assets/<id>/signature` | session | fetch signature |
| GET | `/api/assets/<id>/qr` | session | QR PNG |
| GET | `/label/<id>` | public | printable label page |
| GET | `/asset/<id>` | public | public asset detail page |
| GET/POST | `/api/employees` | admin/rw | list / add employees |
| POST | `/api/employees/ldap-import` | admin | import from AD |
| POST | `/api/employees/ldap-sync` | admin | trigger sync |
| GET/POST/PUT/DELETE | `/api/contracts` | rw+ | contracts |
| GET/POST/DELETE | `/api/locations` | rw+ | locations |
| GET/POST | `/api/tickets` | rw+ | tickets |
| GET/PUT/DELETE | `/api/tickets/<id>` | rw+ | ticket detail |
| POST | `/api/tickets/<id>/reply` | rw+ | reply |
| GET/POST | `/api/users` | admin | list / create users |
| PUT/DELETE | `/api/users/<u>` | admin | edit / delete user |
| GET/PUT | `/api/profile` | session | read / update own profile |
| POST | `/api/profile/password` | session | change own password |
| POST | `/api/profile/avatar` | session | upload avatar (base64, ≤200KB) |
| POST | `/api/profile/apikey` | session | rotate API key |
| GET/PUT | `/api/settings` | admin | read / update system settings |
| GET | `/api/branding` | public | theme/logo for login+sign |
| POST | `/api/logo` | admin | upload logo |
| POST | `/api/settings/smtp-test` | admin | test SMTP |
| GET/POST | `/api/import` / `/api/export` | rw+ | Excel |
| GET | `/api/scan` | admin | network scan |
| GET/POST | `/api/backup` / `/api/backups` / `/api/restore` | admin | backup/restore |
| GET | `/api/audit` | rw+ | audit log |
| GET | `/api/dashboard` | session | dashboard stats |
| GET | `/` , `/<path>` | — | SPA shell |

---

## 11. Operations & Troubleshooting

| Symptom | Cause / Fix |
|---|---|
| `pymysql.err.OperationalError 2003` | MariaDB not running. Start `mysqld` (see 3.2). |
| Editing `app.py` has no effect | `debug=False` = no auto-reload. Kill :5000, relaunch. |
| Changes revert after restart | Settings are persisted in DB; ensure you clicked **SAVE** on System/Customization. Hard-refresh browser cache. |
| Login/sign page ignores theme | Old cached asset. Hard-refresh. Theme comes from `/api/branding`. |
| Sign flow shows "invalid or expired token" | Token expired. Generate a **fresh** SIGN link. |
| PRINT shows "Not signed yet" after signing | Older build dropped `SignatureData`. Current build includes it in the asset API. Hard-refresh. |
| Maintenance "ADD" does nothing | Fixed: `#mAdd` must be wired (current build is). |
| Avatar upload 500 | DB `avatar` column must be `MEDIUMTEXT` (auto-migrated on boot). Route stores base64 data URL. |
| `python3` exits 23 | It's the Windows Store shim. Use the Hermes venv interpreter. |
| LDAP sync not running | Configure LDAP in System settings; auto-sync every 30 min. |

### Logs
Flask prints to the terminal where `app.py` runs. Watch for tracebacks there.

### Backups
Use Backup/Restore (TOOLS) regularly. Store the `.sql` dump off-host.

---

## 12. File Layout

```
C:\Users\Sha\asset-manager\
├── app.py                  # Flask backend + all API routes + DB schema/migrations
├── index.html              # SPA shell (sidebar, pages, modals, tables)
├── app.js                  # Frontend logic (render, actions, theming, API calls)
├── style.css               # Theme (dark/light), compact table, layout
├── login.html              # Login page (themed via /api/branding)
├── (sign page served inline from app.py: /sign)
├── invoices/                # uploaded invoice files
├── logo.png                 # app logo (uploadable)
└── ITGUY_DOCUMENTATION.md   # this file
```

---

## 13. Security Notes
- Passwords hashed (not plaintext) in `Users`.
- Session cookie signed by `ITGUY_SECRET` — **change it** for any non-local use.
- Sign-off tokens are JWT-signed + expiring; the sign page is public by design (so recipients can acknowledge without a login).
- This is a **local** tool; do not expose `:5000` to the internet without a reverse proxy + TLS.
- Admin user cannot be demoted/deleted if it's the last admin (guard in `/api/users`).

---

*Generated from the current source (`app.py`, `index.html`, `app.js`, `style.css`). For the live running instance use `http://127.0.0.1:5000` (admin / admin123).*
