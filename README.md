# IT-Vault

A self-hosted IT asset & helpdesk manager: track assets, employees, checkouts,
maintenance history, support tickets (with a public portal + a live wallboard
monitor), audit logging, LDAP/AD sync, network scanning, and full theming —
built as a Flask backend with a single-file vanilla-JS frontend and MariaDB
for storage.

## Quick start (Docker Compose)

```bash
git clone https://github.com/<owner>/<repo>.git
cd <repo>
cp .env.example .env   # edit the passwords/secret before real use
docker compose up -d
```

Open **http://localhost:5000** and sign in with the admin account from your
`.env` (defaults to `admin` / `admin123` — **change this immediately** if
this isn't just a local trial).

This starts two containers:
- **`db`** — MariaDB 11, schema bootstrapped from `init.sql` on first boot
- **`web`** — the Flask app, waits for the DB to be healthy before starting

## Pull the pre-built image instead of building it

Every push to `main` publishes an image to GitHub Container Registry via the
included Actions workflow (`.github/workflows/docker-publish.yml`):

```bash
docker pull ghcr.io/<owner>/<repo>:main
```

To use it, swap `build: .` for `image: ghcr.io/<owner>/<repo>:main` under the
`web` service in `docker-compose.yml` and run `docker compose up -d` as
above — you still need the `db` service from this compose file (or your own
MariaDB) since the image only contains the app, not the database.

## Configuration

All configuration is environment variables (see `.env.example` for the full
list with defaults) — `DB_HOST` / `DB_PORT` / `DB_NAME` / `DB_USER` /
`DB_PASS` for the database connection, `ITGUY_SECRET` for Flask session
signing, `ITGUY_ADMIN` / `ITGUY_ADMIN_PASS` for the first admin account
(created once, on first DB init — changing these later doesn't touch an
already-created account). Runtime settings that change *inside* the app —
branding, theme colors, SMTP, LDAP, ticket SLAs — live in the database via
Settings → \* in the UI, not in environment variables.

## Database management

- **Storage**: MariaDB runs in its own container with data on a named Docker
  volume (`db_data`), so it survives `docker compose down` / image rebuilds —
  only `docker compose down -v` (or deleting the volume explicitly) destroys
  it. Uploaded invoices and generated `.sql` backups live on their own
  volumes (`invoices_data`, `backups_data`) for the same reason.
- **Schema**: bootstrapped once from `init.sql` on the database's first boot
  (MariaDB only runs `docker-entrypoint-initdb.d/*` against an empty data
  directory — it won't re-run on an existing volume). The app itself also
  runs idempotent `ALTER TABLE`/`CREATE TABLE IF NOT EXISTS` migrations on
  startup for anything added after the initial schema.
- **Backups**: the app has a built-in Backup/Restore page (Settings →
  Backup / Restore, or the sidebar) that exports/imports `.sql` dumps by
  scope (all data, config-only, or assets-only) — this is the easiest path
  for day-to-day use. For a raw external backup instead:
  ```bash
  docker exec itguy-db mysqldump -u itguy -pitguypass itguy_assets > backup.sql
  # restore:
  docker exec -i itguy-db mysql -u itguy -pitguypass itguy_assets < backup.sql
  ```
- **Moving to a managed/external database**: point `DB_HOST` (and the other
  `DB_*` vars) at any reachable MariaDB/MySQL-compatible server and drop the
  `db` service from `docker-compose.yml` — the app doesn't care whether the
  database is in the same compose stack or not.

## Development (without Docker)

```bash
pip install -r requirements.txt
python app.py   # expects a MariaDB reachable via the DB_* env vars
```

## License

Add a license of your choice before treating this as a public template —
none is currently specified.
