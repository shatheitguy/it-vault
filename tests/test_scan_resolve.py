"""A scanned tag resolves to its asset.

The phone's scanner used to hand the code it read to /api/assets?q=, which
searches the visible columns -- and PublicCode is not one of them. So the
scan that worked offline (the phone's own filter does check the code) came
back empty online, and the app showed a list with nothing in it instead of
the asset standing in front of you.

What this pins down is the lookup that replaced it: exact matches on the
three things a printed tag has carried -- the public code, the asset tag, the
id -- and nothing else. Substring matching here would turn one scanned tag
into a way to walk the estate, which is the whole reason the public code
exists.
"""
import os
import sys
import uuid

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


A.app.config["TESTING"] = True
anon = A.app.test_client()
staff = A.app.test_client()
with staff.session_transaction() as sess:
    sess["user"] = "admin"
    sess["role"] = "admin"

AID = "SCN-" + uuid.uuid4().hex[:8]
TAG = "SCN-9001"
CODE = A._new_public_code()
NAME = "Scan resolve fixture"

c = A.conn(); cur = c.cursor()
cur.execute(
    "INSERT INTO Assets (_id, AssetTag, Name, Serial, Status, PublicCode, is_deleted) "
    "VALUES (%s,%s,%s,%s,'Available',%s,0)",
    (AID, TAG, NAME, "SN-SCAN-1", CODE),
)
c.commit(); c.close()

try:
    print("\nresolving a scanned tag")
    for label, ref in (("public code", CODE), ("asset tag", TAG), ("id", AID)):
        r = staff.get("/api/assets/resolve/" + ref)
        body = r.get_json() if r.status_code == 200 else {}
        check("  %-12s resolves to the asset" % label,
              r.status_code == 200 and body.get("_id") == AID,
              "%s %s" % (r.status_code, body.get("_id")))

    r = staff.get("/api/assets/resolve/" + CODE)
    body = r.get_json() or {}
    check("the resolved asset carries what the record screen shows",
          body.get("Name") == NAME and body.get("PublicCode") == CODE,
          body.get("Name"))

    print("\nwhat it refuses")
    r = staff.get("/api/assets/resolve/" + CODE[:4])
    check("a partial code is not a match", r.status_code == 404, r.status_code)

    r = staff.get("/api/assets/resolve/" + TAG[:4])
    check("a partial tag is not a match", r.status_code == 404, r.status_code)

    r = staff.get("/api/assets/resolve/SCN-NOPE-0000")
    check("an unknown tag is a 404, not an empty 200", r.status_code == 404, r.status_code)

    r = anon.get("/api/assets/resolve/" + CODE)
    check("a stranger gets nothing (that is what /p/<code> is for)",
          r.status_code in (401, 403, 302), r.status_code)

    print("\nand the search it replaced")
    r = staff.get("/api/assets?q=" + CODE)
    rows = r.get_json() if r.status_code == 200 else []
    check("the old q= search still cannot see a code -- hence this route",
          all(row.get("_id") != AID for row in rows), len(rows))

    print("\ndeleted assets")
    c = A.conn(); cur = c.cursor()
    cur.execute("UPDATE Assets SET is_deleted=1 WHERE _id=%s", [AID])
    c.commit(); c.close()
    r = staff.get("/api/assets/resolve/" + CODE)
    check("a trashed asset does not resolve", r.status_code == 404, r.status_code)
finally:
    c = A.conn(); cur = c.cursor()
    cur.execute("DELETE FROM Assets WHERE _id=%s", [AID])
    c.commit(); c.close()

print()
if fails:
    print("FAILED (%d): %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("ALL PASSED")
