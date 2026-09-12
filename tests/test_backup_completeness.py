"""A backup has to contain everything that would otherwise be unrecoverable.

Two things it did not.

Invoice attachments. An asset row records the FILENAME; the file itself lives
in its own volume. The archive bundled only the logo and letterhead, so a
restore onto a new host brought back rows pointing at attachments the archive
had never carried.

And automatic backups shipped switched off, which is the setting people find
out about on the day they needed it.

Both are also the shape of the bug that started this: volumes hold the files,
the database holds the names, and nothing noticed when the two came apart.
"""
import io
import os
import sys
import uuid
import zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
import app as A

A.init_db()
A.migrate_schema()

fails = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (("   " + str(detail)) if detail else ""))
    if not cond:
        fails.append(name)


def read(*parts):
    return io.open(os.path.join(ROOT, *parts), encoding="utf-8-sig").read()


A.app.config["TESTING"] = True
cl = A.app.test_client()
with cl.session_transaction() as s:
    s["user"] = "admin"
    s["role"] = "admin"

AID = "BK-" + uuid.uuid4().hex[:6]
PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"

c = A.conn(); cur = c.cursor()
cur.execute("INSERT INTO Assets (_id, AssetTag, Name, Type, Status) VALUES (%s,%s,%s,%s,%s)",
            (AID, "BK-1", "Backup test laptop", "Laptop", "Available"))
c.commit(); c.close()

made = []
try:
    r = cl.post("/api/assets/" + AID + "/invoice",
                data={"file": (io.BytesIO(PDF), "inv.pdf")},
                content_type="multipart/form-data")
    fname = (r.get_json() or {}).get("file")
    check("an invoice can be attached", r.status_code == 200 and bool(fname), fname)
    path = os.path.join(A.INVOICE_DIR, fname)

    print()
    print("1. The archive carries the attachments, not just their names")
    for scope, want in (("all", True), ("assets", True), ("config", False)):
        f = A._run_backup(scope)
        made.append(f)
        p = os.path.join(A.BACKUP_DIR, f)
        inv = []
        if zipfile.is_zipfile(p):
            with zipfile.ZipFile(p) as z:
                inv = [n for n in z.namelist() if n.startswith("invoices/")]
        check("%-7s scope bundles invoices: %s" % (scope, want),
              bool(inv) == want, "%d found in %s" % (len(inv), f))
    # an assets backup has files now, so it cannot be a bare .sql any more
    assets_file = [f for f in made if "_assets_" in f][-1]
    check("an assets backup is an archive, not a bare .sql",
          assets_file.endswith(".zip"), assets_file)

    print()
    print("2. A restore puts them back")
    full = [f for f in made if "_all_" in f][-1]
    data = io.open(os.path.join(A.BACKUP_DIR, full), "rb").read()
    os.remove(path)
    check("the file is gone before restoring", not os.path.exists(path))
    applied, err = A._apply_restore_bytes(data, full)
    check("the restore succeeds", err is None, err)
    check("the attachment is back", os.path.exists(path))
    check("and is the file that went in",
          os.path.exists(path) and io.open(path, "rb").read() == PDF)

    print()
    print("3. A restore does not destroy what is already there")
    # an attachment present locally and absent from the archive must survive
    io.open(path, "wb").write(b"NEWER LOCAL COPY")
    A._apply_restore_bytes(data, full)
    check("an existing file is left alone",
          io.open(path, "rb").read() == b"NEWER LOCAL COPY")

    print()
    print("4. A zip entry cannot write outside the invoice directory")
    src = read("app.py")
    i = src.index("def _restore_invoices(")
    fn_src = src[i:src.index("\n@app.route", i)]
    check("entries are reduced to a basename", "os.path.basename(n)" in fn_src)
    check("and . / .. are refused", 'base in (".", "..")' in fn_src)

    print()
    print("5. Automatic backups are on")
    c = A.conn(); cur = c.cursor()
    cur.execute("SELECT backup_schedule, backup_defaulted FROM Settings WHERE id=1")
    row = cur.fetchone() or {}; c.close()
    check("a schedule is set", (row.get("backup_schedule") or "off") in ("daily", "weekly"),
          row.get("backup_schedule"))
    check("and it is recorded as applied", int(row.get("backup_defaulted") or 0) == 1, row)
    check("new installs ship with it on",
          "\"backup_schedule\": \"VARCHAR(20) DEFAULT 'daily'\"" in src)
    # turning it off must stick -- the migration nudges once, not every start
    c = A.conn(); cur = c.cursor()
    cur.execute("UPDATE Settings SET backup_schedule='off' WHERE id=1")
    c.commit(); c.close()
    A.migrate_schema()
    c = A.conn(); cur = c.cursor()
    cur.execute("SELECT backup_schedule FROM Settings WHERE id=1")
    after = (cur.fetchone() or {}).get("backup_schedule"); c.close()
    check("a deliberate 'off' is not overridden again", after == "off", after)

    print()
    print("6. The app says so when the files are not where the rows expect")
    check("there is a startup check", hasattr(A, "warn_if_invoices_missing"))
    warn = src[src.index("def warn_if_invoices_missing("):]
    warn = warn[:warn.index("\nif __name__")]
    check("it counts rows that expect a file", "InvoiceFile IS NOT NULL" in warn)
    check("it names the directory it looked in", "INVOICE_DIR" in warn)
    check("and points at the volume mix-up", "docker volume ls" in warn)
    check("it is called on the production path",
          "warn_if_invoices_missing()" in read("serve.py"))

    print()
    print("7. The installer adopts volumes an older compose layout left behind")
    sh = read("install.sh")
    check("there is an adopt step", "adopt_orphan_volumes()" in sh)
    check("it runs on update", sh.count("    adopt_orphan_volumes") >= 1)
    check("it runs on a fresh install", sh.count("\nadopt_orphan_volumes") >= 1)
    # copying when both hold data would be a guess about which is current
    check("it only adopts into an empty volume", 'if [ "$_mine" -gt 0 ]; then' in sh)
    check("it copies without overwriting", "cp -an /from/. /to/" in sh)
    check("it never deletes the original", "volume rm" not in sh)
    check("compose still pins its names", read("docker-compose.yml").count("name:") >= 4)
finally:
    c = A.conn(); cur = c.cursor()
    cur.execute("DELETE FROM Assets WHERE _id=%s", (AID,))
    c.commit(); c.close()
    for f in made:
        try:
            os.remove(os.path.join(A.BACKUP_DIR, f))
        except Exception:
            pass
    try:
        os.remove(os.path.join(A.INVOICE_DIR, fname))
    except Exception:
        pass
    print()
    print("(test asset, its attachment and the test backups removed)")

print()
if fails:
    print("FAILED (%d): %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("ALL PASSED")
