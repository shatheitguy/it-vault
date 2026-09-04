# IT-Vault

A self-hosted IT asset & helpdesk manager: track assets, employees, checkouts,
maintenance history, support tickets (with a public portal + a live wallboard
monitor), audit logging, LDAP/AD sync, network scanning, and full theming —
built as a Flask backend with a single-file vanilla-JS frontend and MariaDB
for storage.

## Quick start (Docker Compose)

IT-Vault does not ship a database — you point it at your own. Install
MariaDB (or MySQL) wherever suits you, then create an empty database and a
user for it:

```sql
CREATE DATABASE itvault CHARACTER SET utf8mb4;
CREATE USER 'itvault'@'%' IDENTIFIED BY '<a-strong-password>';
GRANT ALL PRIVILEGES ON itvault.* TO 'itvault'@'%';
```

Then run IT-Vault:

```bash
git clone https://github.com/shatheitguy/it-vault.git
cd it-vault
cp .env.example .env    # optional: fill in the DB_* values
docker compose up -d
```

Open **http://localhost:5000**. A fresh install lands on the first-run setup
wizard: enter your database connection (it's tested before anything is
saved), then create your own administrator account. There is no default
password to change afterwards — nothing can sign in until you make that
account. The schema builds itself, and migrates itself on upgrade.

## Running the published image directly

Every release publishes to GitHub Container Registry, so you don't need a
source checkout at all:

```bash
docker run -d --name itvault -p 5000:5000 \
  -v itvault_data:/app/data \
  -v invoices_data:/app/invoices \
  -v backups_data:/app/backups \
  -e ITVAULT_DATA_DIR=/app/data \
  ghcr.io/shatheitguy/it-vault:1.6.0
```

Then open the setup wizard and enter your database details. Pin a version
tag for anything real; `latest` moves whenever a release is published.

Keep `/app/data` on a volume: it holds the generated session-signing key and
the saved database pointer, so an image update doesn't sign everyone out.

## Configuration

Everything is optional (see `.env.example`). `DB_HOST` / `DB_PORT` /
`DB_NAME` / `DB_USER` / `DB_PASS` set the database connection, but you can
leave them blank and enter it in the setup wizard instead — either way it's
saved to `/app/data` and reconfigurable later in Settings → Database.

`ITVAULT_ADMIN` / `ITVAULT_ADMIN_PASS` create the first admin without the
wizard, for unattended installs; unset, the wizard asks. `ITVAULT_SECRET`
overrides the session-signing key, which is otherwise generated and kept in
`/app/data` — leave it unset unless you're running several replicas that
must share one key.

Runtime settings that change *inside* the app — branding, theme colors,
SMTP, LDAP, ticket SLAs, roles — live in the database via Settings → \* in
the UI, not in environment variables.

## Database

- **You own it.** IT-Vault connects to whatever MariaDB/MySQL you give it —
  bare metal, another container, or a managed instance. It never provisions,
  upgrades or deletes the server, so your backup and retention policy stays
  yours. Change where it points any time in Settings → Database, or via the
  `DB_*` variables.
- **Reaching it from the container**: a database on the same machine is
  `host.docker.internal`; one in another container is that container's
  service name. `127.0.0.1` refers to the IT-Vault container itself and will
  not work.
- **Schema**: created on first start and migrated on every start, so an
  upgrade needs no manual SQL.
- **Backups**: Settings → Backup / Restore exports and restores archives by
  scope (everything, config only, or assets only). An "everything" archive
  includes the uploaded logo and letterhead, which live on disk rather than
  in the database. Restoring clears each table before repopulating it, so it
  reverts to that point in time rather than merging.
- **What's on volumes**: `/app/data` (session key + saved DB pointer),
  `/app/invoices` (uploaded invoices) and `/app/backups` (generated
  archives). These survive `docker compose down`; only `down -v` destroys
  them. Your database lives wherever you installed it and is untouched by
  any of that.

## Development (without Docker)

```bash
pip install -r requirements.txt
python serve.py   # expects a MariaDB reachable via the DB_* env vars
```

## License

Add a license of your choice before treating this as a public template —
none is currently specified.
