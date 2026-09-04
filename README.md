# IT-Vault

A self-hosted IT asset & helpdesk manager: track assets, employees, checkouts,
maintenance history, support tickets (with a public portal + a live wallboard
monitor), audit logging, LDAP/AD sync, network scanning, and full theming —
built as a Flask backend with a single-file vanilla-JS frontend and MariaDB
for storage.

## Step 1 — get a database

IT-Vault ships without one, so it never dictates your database's version,
backups or retention. Any MariaDB 10.6+ (or MySQL 8+) works. Pick whichever
of these suits you.

### Option A — MariaDB as a Docker container

Quickest if you already run Docker:

```bash
docker volume create itvault_db

docker run -d --name itvault-db --restart unless-stopped \
  -e MARIADB_ROOT_PASSWORD='<a-strong-root-password>' \
  -e MARIADB_DATABASE=itvault \
  -e MARIADB_USER=itvault \
  -e MARIADB_PASSWORD='<a-strong-password>' \
  -v itvault_db:/var/lib/mysql \
  mariadb:11
```

That creates the database and user for you, so you can skip the SQL below.
Keep the volume — it *is* your data. Don't publish port 3306 unless you
genuinely need outside access; IT-Vault reaches it over the Docker network.

To let the two containers talk, put them on one network:

```bash
docker network create itvault-net
docker network connect itvault-net itvault-db
```

…then attach IT-Vault to `itvault-net` too, and use **`itvault-db`** as the
database host.

### Option B — MariaDB on a server or your own machine

Better if you already run a database server, or want it outside Docker.

```bash
# Debian / Ubuntu
sudo apt install mariadb-server

# RHEL / Rocky / Fedora
sudo dnf install mariadb-server && sudo systemctl enable --now mariadb

# macOS
brew install mariadb && brew services start mariadb
```

On Windows, use the installer from [mariadb.org/download](https://mariadb.org/download/)
and **let it install as a service** so it starts at boot — otherwise it dies
with the session that started it.

Then run `sudo mariadb-secure-installation` (set a root password, remove the
anonymous users) and create the database:

```sql
CREATE DATABASE itvault CHARACTER SET utf8mb4;
CREATE USER 'itvault'@'%' IDENTIFIED BY '<a-strong-password>';
GRANT ALL PRIVILEGES ON itvault.* TO 'itvault'@'%';
FLUSH PRIVILEGES;
```

Restrict the host if you can: `'itvault'@'localhost'` for a database on the
same machine, or `'itvault'@'172.17.%'` for the Docker bridge, instead of
`'%'` which allows connections from anywhere.

### Which host does IT-Vault use?

This is the one thing people get wrong. From inside the IT-Vault container,
`127.0.0.1` means *the container itself*, not your machine:

| Where the database runs | `DB_HOST` |
|---|---|
| Docker container on the same network | that container's name, e.g. `itvault-db` |
| Same machine, outside Docker | `host.docker.internal` |
| Another server | its hostname or IP |
| IT-Vault also running outside Docker | `127.0.0.1` |

## Step 2 — run IT-Vault

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
