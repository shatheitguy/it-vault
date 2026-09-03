"""Production entry point: same startup work as `python app.py`, then serves
through waitress instead of Flask's development server.

`python app.py` runs Flask's built-in dev server -- single process, not
built for concurrent load, and it says so in its own startup banner. That
was what the container actually ran, even though waitress was already a
dependency.

The startup steps below (schema init/migration and the three background
schedulers) live in app.py's `if __name__ == "__main__"` block, so they do
NOT happen on a bare `waitress-serve app:app` -- no migrations, no LDAP
auto-sync, no scheduled backups, no contract-expiry alerts. Hence this
file rather than a CMD one-liner.
"""
import os

from waitress import serve

import app as _app


def main():
    _app.init_db()
    _app.migrate_schema()
    _app.start_ldap_scheduler()
    _app.start_backup_scheduler()
    _app.start_contract_expiry_scheduler()

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 5000))
    # threads: waitress' worker count. The DB pool's maxconnections (32) is
    # set above this so workers don't queue waiting for a connection.
    threads = int(os.environ.get("WAITRESS_THREADS", 8))
    print(f"IT-Vault (MariaDB) -> http://{host}:{port}  [waitress, {threads} threads]")
    serve(_app.app, host=host, port=port, threads=threads, ident="IT-Vault")


if __name__ == "__main__":
    main()
