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
import time

from waitress import serve

import app as _app


def wait_for_db(timeout_s: int = 300) -> None:
    """Blocks until the database answers, instead of dying if it isn't up yet.

    init_db()/migrate_schema() below both need the database, so without this
    a server started while MariaDB is still coming up (or briefly down) exits
    immediately and stays down until someone restarts it by hand -- the app
    never opens its port at all.

    Deliberately uses app.conn(), so it honours whatever DB config the app
    itself resolved (nexus_config.json, then environment). The repo's
    wait_for_db.py reads environment variables only and defaults to the
    Docker service name, so it can't stand in for this outside a container.
    """
    deadline = time.time() + timeout_s
    attempt = 0
    while True:
        try:
            c = _app.conn()
            c.close()
            if attempt:
                print(f"[serve] database reachable after {attempt} attempt(s)")
            return
        except Exception as e:
            attempt += 1
            if time.time() >= deadline:
                print(f"[serve] database still unreachable after {timeout_s}s -- giving up")
                raise
            print(f"[serve] waiting for database ({type(e).__name__}); retry {attempt}...", flush=True)
            time.sleep(min(5, attempt))


def main():
    wait_for_db(int(os.environ.get("DB_WAIT_SECONDS", 300)))
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
