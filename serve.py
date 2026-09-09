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
    itself resolved -- itvault_config.json (written by the setup wizard)
    first, then the environment. A wait that only read env vars couldn't see
    a database configured through the wizard at all.
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


def _warn_if_data_not_persistent():
    """Say so, loudly, before anything is lost.

    Without `-v itvault_data:/app/data` the saved database pointer and the
    session key live in the container's writable layer, so replacing the
    container -- which is how an update happens -- throws them away and the
    next start comes up on the setup wizard with everyone signed out. That is
    a miserable thing to discover mid-upgrade, so it goes in the log on every
    boot instead.
    """
    try:
        if _app.IS_DOCKER and not _app._data_dir_persistent():
            bar = "!" * 72
            print(bar, flush=True)
            print("[serve] WARNING: " + _app.DATA_DIR + " is NOT a mounted volume.", flush=True)
            print("[serve] The saved database settings and session key will be LOST when this",
                  flush=True)
            print("[serve] container is replaced -- which is exactly how updating works.",
                  flush=True)
            print("[serve] Re-create it with:  -v itvault_data:/app/data", flush=True)
            print(bar, flush=True)
    except Exception:
        pass          # a warning must never be the thing that stops startup


def main():
    _warn_if_data_not_persistent()
    # A brand-new container has no database configured yet, and the setup
    # wizard is served BY this process -- so a missing database can't be
    # fatal here or there'd be nowhere to enter one. Wait briefly for a
    # database that's merely still starting, then start regardless: app.py
    # serves /setup until one is configured and an admin exists.
    try:
        wait_for_db(int(os.environ.get("DB_WAIT_SECONDS", 90)))
        _app.init_db()
        _app.migrate_schema()
        # The database answered, so the credentials that got us here are worth
        # keeping. Without this they live only in the container's environment
        # and `docker rm -f itvault` sends the next start back to the wizard.
        _app.persist_env_db_config()
    except Exception as e:
        print(f"[serve] no database yet ({type(e).__name__}) -- starting in setup mode; "
              f"open /setup to configure one", flush=True)
    _app.start_ldap_scheduler()
    _app.start_backup_scheduler()
    _app.start_heartbeat_runner()    # runs IT-Vault's own checks
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
