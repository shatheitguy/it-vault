"""However you installed it, the next update must not break the database.

The saved pointer normally wins over the environment -- that is what makes a
database survive its container being replaced. The risk is the mirror image:
a pointer that stops being true can no longer be corrected from outside the
volume, and the install sits on the setup wizard. These check both halves.
"""
import io
import json
import os
import shutil
import sys
import tempfile

DATA = os.path.join(tempfile.gettempdir(), "itvault_reconcile_data")
shutil.rmtree(DATA, ignore_errors=True)
os.makedirs(DATA, exist_ok=True)
os.environ["ITVAULT_DATA_DIR"] = DATA

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
REAL = json.load(io.open(os.path.join(ROOT, "itvault_config.json"), encoding="utf-8"))

sys.path.insert(0, ROOT)
os.chdir(ROOT)

fails = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (("   " + str(detail)) if detail else ""))
    if not cond:
        fails.append(name)


def write_cfg(d):
    io.open(os.path.join(DATA, "itvault_config.json"), "w", encoding="utf-8").write(json.dumps(d))


print("1. A saved pointer that WORKS is never second-guessed")
write_cfg(REAL)
for k in ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASS", "DB_PORT"):
    os.environ.pop(k, None)
os.environ["DB_HOST"] = "somewhere-else.invalid"
os.environ["DB_NAME"] = REAL["db_name"]
os.environ["DB_USER"] = REAL["db_user"]
os.environ["DB_PASS"] = REAL["db_pass"]

import app as A                                    # noqa: E402  (env first)

check("it loaded the saved pointer, not the environment",
      A.DB_HOST == REAL["db_host"], f"{A.DB_HOST!r}")
check("the saved pointer actually connects",
      A._db_reachable(A.DB_HOST, A.DB_PORT, A.DB_NAME, A.DB_USER, A.DB_PASS))
# the environment here is deliberately broken, so reconciling must decline
check("reconcile declines when the environment is worse",
      A.reconcile_db_config() is False)
check("and the pointer is untouched", A.DB_HOST == REAL["db_host"], A.DB_HOST)

print("\n2. A saved pointer that has STOPPED working yields to the environment")
# what a networking change looks like: the file names a host that is gone
A.save_db_config("itvault-db-that-no-longer-exists", 3306,
                 REAL["db_name"], REAL["db_user"], REAL["db_pass"])
A._cfg["db_host"] = "itvault-db-that-no-longer-exists"
check("the app is now pointed at a dead host",
      A._db_reachable(A.DB_HOST, A.DB_PORT, A.DB_NAME, A.DB_USER, A.DB_PASS) is False)
# and the environment carries the truth
os.environ["DB_HOST"] = REAL["db_host"]
os.environ["DB_PORT"] = str(REAL["db_port"])
check("reconcile follows the environment", A.reconcile_db_config() is True)
check("the app is repointed", A.DB_HOST == REAL["db_host"], A.DB_HOST)
check("it can connect again",
      A._db_reachable(A.DB_HOST, A.DB_PORT, A.DB_NAME, A.DB_USER, A.DB_PASS))
saved = json.load(io.open(os.path.join(DATA, "itvault_config.json"), encoding="utf-8"))
check("and the file on disk was corrected", saved["db_host"] == REAL["db_host"], saved.get("db_host"))
check("the pool follows too (a real query works)",
      (lambda: (A.conn().close() or True))(), "connected through the pool")

print("\n3. With no environment at all, nothing is changed")
for k in ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASS", "DB_PORT"):
    os.environ.pop(k, None)
before = A.DB_HOST
check("reconcile is a no-op", A.reconcile_db_config() is False)
check("pointer unchanged", A.DB_HOST == before)

print("\n4. The pointer is still written on a first successful connection")
os.remove(os.path.join(DATA, "itvault_config.json"))
A._cfg.clear()
A._db_pointer_saved = False
os.environ["DB_HOST"] = REAL["db_host"]
os.environ["DB_NAME"] = REAL["db_name"]
os.environ["DB_USER"] = REAL["db_user"]
os.environ["DB_PASS"] = REAL["db_pass"]
A.conn().close()
exists = os.path.exists(os.path.join(DATA, "itvault_config.json"))
check("saved on first use, with no wizard involved", exists)
if exists:
    got = json.load(io.open(os.path.join(DATA, "itvault_config.json"), encoding="utf-8"))
    check("and it holds the working credentials", got["db_host"] == REAL["db_host"], got.get("db_host"))

print("\n" + ("ALL PASSED" if not fails else f"{len(fails)} FAILED: " + "; ".join(fails)))
raise SystemExit(1 if fails else 0)
