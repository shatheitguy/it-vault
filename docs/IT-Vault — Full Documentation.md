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
- **Heartbeat** — uptime monitoring of devices and services (ping / HTTP / keyword / TCP port / DNS) with alerting and retained history.
- **Audit Log**, **Network Scan**, **Backup/Restore**, **Import/Export Excel**.

Stack: Python 3 (Flask), MariaDB 12.3, Jinja-free server-rendered HTML + vanilla JS SPA, openpyxl for Excel, ldap3 for AD sync, qrcode for labels.

---

## 2. Architecture

```
Browser (index.html SPA, app.js, style.css, login.html, /sign, /label/<id>, /asset/<id>)
        │  HTTP / JSON API + cookie session
        ▼
Flask app (app.py)  ── pymysql ──▶ MariaDB (db: itvault)
        │
        ├─ openpyxl  (Excel import/export)
        ├─ ldap3     (AD/LDAP employee sync)
        └─ qrcode    (asset QR labels, rendered to PNG)

MariaDB on 127.0.0.1:3306  (you provide it; install it as a service so it
                            starts at boot. IT-Vault never manages the
                            database server, only the schema inside it.)
```

### Processes
- **Flask dev server** — `python app.py` → listens on `127.0.0.1:5000`. `debug=False`, so **no auto-reload**; after editing `app.py` you must kill the process on :5000 and relaunch.
- **MariaDB** — must be running before Flask starts, or DB calls fail with `pymysql 2003`.
- **Heartbeat runner** — a daemon thread started by `serve.py` (`start_heartbeat_runner()`). Ticks every 5 s and probes any monitor whose `next_check` has come round, for as long as the app runs. A monitor row is claimed before it is probed, so two instances sharing one database cannot double-alert on the same outage.

---

## 3. Installation & First Run

### 3.1 Prerequisites
- Windows 10/11
- Python 3.11+ (a virtualenv is recommended: `python -m venv .venv`)
- MariaDB 10.6+ (any recent release; the examples below use a Windows install path)
- Python packages: `flask`, `pymysql`, `openpyxl`, `ldap3`, `qrcode`, `pillow`

> ⚠️ On Windows, the `python3` on PATH may be the Microsoft Store shim, which exits immediately with code 23. Use your virtualenv's interpreter.

### 3.1b On a NAS

**Unraid** — Community Applications, search IT-Vault. Install MariaDB first
(the CA template is fine), create an empty database and a user for it, then
fill in the database fields or leave them empty and let the first-run wizard
ask. The template is published from
[shatheitguy/unraid-templates](https://github.com/shatheitguy/unraid-templates);
its source lives in `unraid/it-vault.xml` in this repository, where the test
suite checks it against the code.

**TrueNAS** (24.10 and later, which runs Docker Compose) — Apps → Discover
Apps → Custom App → Install via YAML, and paste
`truenas/docker-compose.yaml`. That file brings MariaDB with it, so there is
nothing to set up first; edit the four values marked EDIT and the dataset
paths before you save.

### 3.2 Get a database running
IT-Vault ships without one. Any MariaDB 10.6+ or MySQL 8+ works — pick one:

**As a Docker container** (creates the database and user for you):

```bash
docker volume create itvault_db
docker run -d --name itvault-db --restart unless-stopped \
  -e MARIADB_ROOT_PASSWORD='<root-password>' \
  -e MARIADB_DATABASE=itvault \
  -e MARIADB_USER=itvault -e MARIADB_PASSWORD='<a-strong-password>' \
  -v itvault_db:/var/lib/mysql mariadb:11
```

**On a server or workstation**: `apt install mariadb-server` (Debian/Ubuntu),
`dnf install mariadb-server` (RHEL family), `brew install mariadb` (macOS), or
the installer from mariadb.org on Windows. Then `mariadb-secure-installation`.

> ⚠️ On Windows, install it **as a service** so it starts at boot. Started by
> hand from a console it dies with that session, and IT-Vault then can't reach
> it — a slow-burning source of "the app was working yesterday".

Verify it's listening:

```
netstat -ano | findstr :3306      # Windows
ss -lntp | grep 3306              # Linux
```

### 3.3 Create the database & user (one-time)
Using the MariaDB client:

```sql
CREATE DATABASE IF NOT EXISTS itvault CHARACTER SET utf8mb4;
CREATE USER IF NOT EXISTS 'itvault'@'127.0.0.1' IDENTIFIED BY '<a-strong-password>';
GRANT ALL PRIVILEGES ON itvault.* TO 'itvault'@'127.0.0.1';
FLUSH PRIVILEGES;
```

### 3.4 Start the app
```bash
cd /path/to/it-vault
# kill any old process on :5000 first
for pid in $(netstat -ano | grep ":5000" | findstr LISTENING | awk '{print $5}'); do taskkill /PID $pid /F; done

# launch with the venv interpreter (background)
python serve.py
```

On first launch `init_db()` auto-creates all tables and seeds the admin user.

### 3.5 Default login
- **URL:** `http://127.0.0.1:5000`
- **Username:** `admin`
- **Password:** the one you set in the first-run wizard

> Change these via env vars `ITVAULT_ADMIN` / `ITVAULT_ADMIN_PASS` or in code (`ADMIN_USER`/`ADMIN_PASS`).

---

## 4. Configuration

All config is read from environment variables (Docker-friendly), with local defaults:

| Env var | Default | Purpose |
|---|---|---|
| `DB_HOST` | `127.0.0.1` | MariaDB host |
| `DB_PORT` | `3306` | MariaDB port |
| `DB_NAME` | `itvault` | Database name |
| `DB_USER` | `itvault` | DB user |
| `DB_PASS` | _(required)_ | DB password |
| `ITVAULT_SECRET` | generated + persisted to `.secret_key` | Flask session signing secret |
| `ITVAULT_ADMIN` | `admin` | Default admin username |
| `ITVAULT_ADMIN_PASS` | _(unset)_ | Only for an unattended install; unset means the first-run wizard asks instead |

The older `ITGUY_SECRET` / `ITGUY_ADMIN` / `ITGUY_ADMIN_PASS` names are still
read when the `ITVAULT_*` ones are unset, so existing deployments keep working.

System-wide settings (persisted in the `Settings` table, row id=1) are editable from the **System** page: theme, app name, logo text, matrix animation, SMTP (notifications), language, currency, region, notification toggles, QR/label size, LDAP server credentials.

---

## 5. Data Model (MariaDB `itvault`)

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
- **HeartbeatMonitors** (`id`, `name`, `kind` [ping|http|keyword|port|dns], `target`, `port`, `interval_s`, `fail_threshold`, `timeout_s`, `retry_interval_s`, `resend_every`, `enabled`, `notify`, `upside_down`, `ignore_tls`, `keyword`, `keyword_invert`, `accepted_codes`, `http_method`, `tag`, `channels`, `note`, `cert_days`, `asset_id`, `status`, `fails`, `last_ms`, `last_error`, `last_check`, `last_change`, `next_check`)
- **HeartbeatSamples** (`id`, `monitor_id`, `monitor`, `ts`, `status`, `response_ms`) — one row per check. Kept indefinitely unless `ITVAULT_HB_RETAIN_DAYS` is set.
- **HeartbeatHourly** (`monitor_id`, `hour` PK, `checks`, `ups`, `sum_ms`, `min_ms`, `max_ms`) — roll-up written as checks land, never pruned; what the long uptime windows read.
- **HeartbeatEvents** (`id`, `monitor_id`, `ts`, `kind` [created|up|down|paused|resumed], `message`) — the incident log.
- **HeartbeatChannels** (`id`, `name`, `kind` [email|webhook|slack|telegram], `config` JSON, `enabled`, `created_at`) — where alerts go. Empty table = fall back to the notification address in Settings.
- **Settings** (row id=1): theme, smtp_*, notify_new, notify_delete, app_name, logo_text, matrix_on, ldap_*, qr_size, qr_fields, label_size, label_logo, org_contact, plus `logo` / `letterhead` (MEDIUMBLOB — the database is the source of truth for branding; the files in `DATA_DIR` are only a cache)

---

## 6. Authentication & Roles

Session-based (Flask `session` cookie, signed by `ITVAULT_SECRET`).

| Role | Value | Permissions |
|---|---|---|
| **Admin** | `admin` | Everything: users, settings, LDAP, assets CRUD, tickets, contracts, etc. |
| **Read-Write** | `read-write` | Assets/contracts/tickets CRUD; **no** user/settings/LDAP management |
| **Read-Only** | `read-only` | View + change own password only |

Auth decorator: `@auth_required([ROLE_ADMIN, ROLE_EDIT])` etc. The sign-off page (`/s/<code>`, and the older `/sign?token=`) is **public** by design — the person acknowledging an asset does not have a login. What makes it safe is that the code is unguessable, single use and short-lived, not that the page is hidden.

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
- **Columns** popover (▦) to toggle visible columns (persisted in `localStorage` key `itvault_cols`).
- Per-row actions (role-gated): **SIGN**, **EDIT**, **CHECKOUT**, **MAINT**, **QR**, **DEL** (and **PRINT**).
- Search box, filters, bulk actions.

### Asset row actions
| Button | What it does |
|---|---|
| **SIGN** | Opens the public acknowledgement flow (a short `/s/<code>` link generated via `/api/assets/<id>/sign/link`); after sign-off the signature is stored in `SignatureData`. |
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
2. The recipient gets a short link, `/s/<code>` — a code resolved server-side,
   single use, seven days, one live link per asset. (Before 2.4.0 this was
   `/sign?token=...`; those links still work until they expire. The change was
   forced by mail security, which rewrote and then refused the long form.)
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
- `GET /api/backup?scope=...` → downloads the backup (`config`, `assets`, `all`).
- `GET /api/backups` → lists stored backups.
- `POST /api/restore` → restores from an uploaded dump or archive.

What an `all` backup contains: **every base table in the schema**, read from
`information_schema` rather than a list kept by hand, so a table added by a
new feature is included without anybody remembering to add it. The one
deliberate exclusion is `HeartbeatSamples` (raw per-check telemetry, written
every few seconds and never pruned; it rolls up into `HeartbeatHourly`,
which *is* included). Alongside the dump, the archive carries the logo, the
letterhead and every invoice attachment — those live in volumes, so a dump
alone would restore rows pointing at files that were never in the backup.
Binary columns, ticket attachments included, are written as hex literals so
they round-trip exactly.

Automatic backups are on by default (daily, keeping the last 7). Two places
take one without being asked:

- **Before an update.** `install.sh` asks the running container for a full
  backup before it replaces it. An update does not touch the volumes, so
  this is not insurance against the update itself — it is the "what did this
  look like before" that is impossible to reconstruct afterwards.
- **Before the audit log is cleared**, and before a factory reset. Both
  refuse to proceed if the backup fails.

### 8.10b What overwrites what

The rule: **nothing but a person overwrites what a person typed.** Three
mechanisms enforce it.

*A field you edit becomes yours.* Editing an employee records that column in
`Employees.manual_fields`, and the Active Directory sync stops writing it.
Before this, a job title typed into IT-Vault because AD had the old one was
replaced by AD's answer at the next sync, half an hour later; retyping did
not help, because the next sync undid that too.

*A directory with no answer does not get to erase.* AD returns `""` for an
attribute a user does not have. The sync writes only non-empty values, so a
person with no `title` in AD keeps whatever IT-Vault holds. The sync result
reports this as "left as entered".

*An absent field is not an instruction to clear one.* `PUT /api/assets/<id>`
and `PUT /api/employees/<id>` write only the columns present in the request
body. The web forms post whole records, but the phone app, an import and
anything holding an API key send what they changed — and a status update
that also emptied the serial number and the warranty is not an update.
Clearing a field on purpose still works: send it as `""`. The difference
between an empty string and an absent key is the whole distinction.

Every employee change is written to the audit log field by field, with the
value it had before, so a value that does change can be traced to who
changed it and when. `tests/test_no_silent_blanking.py` holds all of this.

### 8.11 LDAP / Active Directory Sync
Configured in **System** settings (LDAP server, domain, bind user, base DN). `POST /api/ldap/test` validates; `POST /api/employees/ldap-import` pulls users; a background scheduler auto-syncs every 30 min (`POST /api/employees/ldap-sync`).

The sync adds people it has not seen, and fills in name, department,
designation and email for anyone nobody has edited. It never writes an empty
value and never overwrites a field edited in IT-Vault — see 8.10b. Its
result is `{added, updated, kept, total}`, where `kept` counts the rows it
deliberately left as entered.


### 8.12 Heartbeat (uptime monitoring)

**Tools → Network Scan → Heartbeat.** Separate permission: `tools.heartbeat`, so a role can have the network scan without this, or the reverse.

Check types: `ping` (ICMP), `http` (accepted status codes, default `200-299`), `keyword` (fetches the body and looks for a string, optionally inverted), `port` (TCP connect), `dns` (resolves a name).

**The flap guard is the point.** A monitor must fail `fail_threshold` consecutive checks before its status becomes `down`; until then it sits at `pending`. Alerts are sent on the *transition* only — once on the way down, once on recovery — plus an optional reminder every `resend_every` further failures. While a monitor is down it is re-checked on `retry_interval_s` instead of `interval_s`.

`upside_down` inverts the verdict, for something that is supposed to *not* respond. HTTPS monitors also record days until certificate expiry, which is reported separately and never fails the check.

History: uptime over 24 h / 7 d / 30 d / 1 y comes from `HeartbeatHourly`; the response chart reads raw samples for windows ≤ 48 h and the roll-up beyond that.
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
| GET | `/api/heartbeat/state` | `tools.heartbeat` | monitors, counts, recent checks, channels |
| GET/POST | `/api/heartbeat/monitors` | `tools.heartbeat` | list / create a monitor |
| PUT/DELETE | `/api/heartbeat/monitors/<id>` | `tools.heartbeat` | update (partial — omitted or null fields keep their stored value) / delete |
| GET | `/api/heartbeat/monitors/<id>/detail` | `tools.heartbeat` | uptime windows, chart series, event log |
| POST | `/api/heartbeat/check` | `tools.heartbeat` | probe everything now |
| POST | `/api/heartbeat/monitors/<id>/check` | `tools.heartbeat` | probe one now |
| GET/POST | `/api/heartbeat/channels` | admin | list / create an alert channel |
| PUT/DELETE | `/api/heartbeat/channels/<id>` | admin | update / delete a channel |
| POST | `/api/heartbeat/channels/<id>/test` | admin | send a test alert |
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
| Logo / letterhead disappeared | The database holds the real copy; the files in `DATA_DIR` are a cache. Run `docker exec itvault python brand_doctor.py` and read section 5b — if it says *cached but not in the database*, re-upload once. |
| A monitor alerts repeatedly | Raise `fail_threshold`, or set `resend_every` back to 0. Alerts fire on transitions; a reminder interval is opt-in. |
| No alert arrived | Check **Alerts** on the Heartbeat page and use each channel's Test button. With no channel configured, alerts use the notification address in Settings, which needs SMTP. |
| Changes revert after restart | Settings are persisted in DB; ensure you clicked **SAVE** on System/Customization. Hard-refresh browser cache. |
| Login/sign page ignores theme | Old cached asset. Hard-refresh. Theme comes from `/api/branding`. |
| Sign flow shows "invalid or expired token" | Token expired. Generate a **fresh** SIGN link. |
| PRINT shows "Not signed yet" after signing | Older build dropped `SignatureData`. Current build includes it in the asset API. Hard-refresh. |
| Maintenance "ADD" does nothing | Fixed: `#mAdd` must be wired (current build is). |
| Avatar upload 500 | DB `avatar` column must be `MEDIUMTEXT` (auto-migrated on boot). Route stores base64 data URL. |
| `python3` exits 23 | It's the Windows Store shim. Use your virtualenv's interpreter. |
| LDAP sync not running | Configure LDAP in System settings; auto-sync every 30 min. |

### Logs
Flask prints to the terminal where `app.py` runs. Watch for tracebacks there.

### Backups
Automatic backups are on by default (daily, last 7 kept), and an update takes
one first. Store a copy off-host anyway: retention prunes, and a host that
loses its volumes loses the backups with them. 8.10 lists what an archive
contains.

---

## 12. File Layout

```
it-vault/
├── app.py                  # Flask backend + all API routes + DB schema/migrations
├── index.html              # SPA shell (sidebar, pages, modals, tables)
├── app.js                  # Frontend logic (render, actions, theming, API calls)
├── style.css               # Theme (dark/light), compact table, layout
├── login.html              # Login page (themed via /api/branding)
├── (sign page served inline from app.py: /sign)
├── invoices/                # uploaded invoice files
├── logo.png                 # app logo (uploadable)
└── IT-Vault — Full Documentation.md   # this file
```

---

## 13. Security Notes

Current as of 2.4.0. Where something changed recently it says so, because the
old behaviour is what you will find written down elsewhere.

**Passwords** are stored as PBKDF2-HMAC-SHA256 at 600,000 rounds, salted per
password, with the round count inside the stored value so it can be raised
later. They were one round of salted SHA-256 until 2.3.0 — fast enough to
brute-force on a GPU at billions of guesses a second. Old hashes still verify
and are replaced the next time their owner signs in, which is the only moment
the password is in hand.

**Logging in** is rate limited: ten failures for one account from one address
inside fifteen minutes and that pair has to wait. A correct password clears
the count. Failures and throttling both go to the audit log.

**Sessions** are signed with a key the app generates on first start and keeps
in the data directory (`ITVAULT_DATA_DIR`), so it survives updates and never
lands in a config file. Set `ITVAULT_SECRET` only to share one key across
several instances. The cookie is HttpOnly and SameSite=Lax, and is marked
Secure on any request that arrived over TLS — including behind a proxy, via
`X-Forwarded-Proto`. `ITVAULT_COOKIE_SECURE=1` insists on it always.

**Acknowledgement links** are a short opaque code in the path — `/s/<code>` —
resolved server-side against the `SignLinks` table. They are single use, one
live link per asset, and expire after seven days; issuing a new one retires
the last. Until 2.4.0 the link carried a signed token in the query string,
which mail security rewrote and sometimes refused outright, and which anyone
could base64-decode to read the asset name. Those older links are still
honoured until they expire.

**Signatures** are personal data. `/api/assets/<id>/signature` requires Assets
*read* (it accepted any logged-in account before 2.3.0), the public tag page
never includes one, and the signed PDF omits the price. They are stored
unencrypted in `Assets.SignatureData` and are included in backups — treat a
backup file accordingly.

**API keys** are per user and carry that user's permissions exactly, which is
how an agent is scoped (see §14). They are stored in the clear in
`Users.api_key`; a backup therefore contains working credentials.

**Uploads**: ticket attachments from the public portal are checked by magic
bytes, capped at 4 MB and 4 per ticket, and SVG is refused because it carries
script. Invoice uploads are checked by extension only and served from the
app's own origin.

**Still open**, and worth knowing about: no global `X-Frame-Options` or CSP;
invoices are not content-sniffed and are served inline; API keys and backups
are unencrypted; there is no retention policy for signatures.

**Deployment**: this is a LAN tool by default. Put a reverse proxy with TLS in
front of anything reachable from outside, and set `ITVAULT_PUBLIC_URL` so the
links in emails point at the address people can actually reach.

## 14. Agents (MCP)

IT-Vault ships an MCP server (`mcp/` in the repository) so an agent can work
the register: find a device, see who has it, assign it, take it back, raise
and answer tickets, chase expiring contracts, handle Lost & Found reports.

It runs on the agent's side and talks to this server over the same HTTP API
the apps use, authenticated with an API key — so **an agent has exactly the
permissions of the user that key belongs to, and nothing more**. Two switches
narrow it further: `ITVAULT_MCP_READONLY=1` refuses every write whatever the
key could do, and `trash_asset` needs `ITVAULT_MCP_ALLOW_DELETE=1`.

Wiring for Hermes, OpenClaw, ZeroClaw, Claude Desktop, Claude Code and ChatGPT
is in `mcp/README.md`. Clients that connect over the network rather than
spawning a process (ChatGPT, Claude's custom connectors) use the HTTP
transport, which refuses to bind anywhere but loopback without a bearer token.

---

*Written against the source at 2.4.0 (`app.py`, `index.html`, `app.js`, `style.css`).*
