"""A sign link is single use, and lives seven days until it is used.

Signing used to leave the link working, so the same acknowledgement could be
submitted again and overwrite the signature already on record. And the link
was issued with exp_hours=7 -- seven HOURS -- so one emailed on a Friday
afternoon was dead before anyone opened it on Monday.
"""
import base64
import io
import json
import os
import sys
import time
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


def png():
    from PIL import Image
    import io as _io
    b = _io.BytesIO()
    im = Image.new("RGBA", (200, 60), (0, 0, 0, 0))
    for x in range(10, 190):
        im.putpixel((x, 30), (0, 0, 0, 255))
    im.save(b, "PNG")
    return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()


A.app.config["TESTING"] = True
admin = A.app.test_client()
with admin.session_transaction() as s:
    s["user"] = "admin"
    s["role"] = "admin"
anon = A.app.test_client()          # the employee: no session at all

aid = "LINKTEST-" + uuid.uuid4().hex[:6]
c = A.conn(); cur = c.cursor()
cur.execute("INSERT INTO Assets (_id, AssetTag, Name, Type, Status) VALUES (%s,%s,%s,%s,%s)",
            (aid, "LNK-1", "Link lifecycle", "Laptop", "Available"))
c.commit(); c.close()


def nonce_on_asset():
    c = A.conn(); cur = c.cursor()
    cur.execute("SELECT SignNonce FROM Assets WHERE _id=%s", [aid])
    v = (cur.fetchone() or {}).get("SignNonce") or ""
    c.close()
    return v


print("1. Issuing a link")
r = admin.get(f"/api/assets/{aid}/sign/link")
check("the link is issued", r.status_code == 200, r.get_data(as_text=True)[:120])
tok = (r.get_json() or {}).get("token") or ""
check("a token comes back", bool(tok))
payload = json.loads(base64.urlsafe_b64decode(tok.rsplit(".", 1)[0] + "==").decode())
check("it carries a nonce", bool((payload.get("a") or {}).get("n")), payload)
check("the asset holds the same nonce", nonce_on_asset() == payload["a"]["n"])

life_days = (payload["exp"] - time.time()) / 86400.0
check("it lives 7 days, not 7 hours", 6.9 < life_days < 7.1, f"{life_days:.2f} days")

print("\n2. Before signing, the link works -- repeatedly")
for i in (1, 2):
    r = anon.get(f"/api/assets/sign/verify?token={tok}")
    j = r.get_json() or {}
    check(f"open #{i} succeeds", r.status_code == 200 and j.get("ok") is True,
          j.get("error"))

print("\n3. Signing it")
A.send_notification = lambda *a, **k: True      # no SMTP in a test
r = anon.post("/api/assets/sign/approve",
              json={"token": tok, "name": "Ancil Test", "data": png()})
j = r.get_json() or {}
check("the acknowledgement is accepted", r.status_code == 200 and j.get("ok") is True,
      j.get("error"))
check("the nonce is cleared, so the link is spent", nonce_on_asset() == "",
      repr(nonce_on_asset()))

c = A.conn(); cur = c.cursor()
cur.execute("SELECT Status, ReceivedBy, LENGTH(SignatureData) n FROM Assets WHERE _id=%s", [aid])
row = cur.fetchone(); c.close()
check("the signature is on record", (row.get("n") or 0) > 100, row.get("n"))
check("and the asset is checked out to them",
      row.get("Status") == "Checked-Out" and row.get("ReceivedBy") == "Ancil Test", row)

print("\n4. After signing, the SAME link is refused")
r = anon.get(f"/api/assets/sign/verify?token={tok}")
j = r.get_json() or {}
check("opening it is refused", r.status_code == 400 and j.get("ok") is False, j)
check("and it says why, in plain words", "already been used" in (j.get("error") or ""),
      j.get("error"))

r = anon.post("/api/assets/sign/approve",
              json={"token": tok, "name": "Someone Else", "data": png()})
j2 = r.get_json() or {}
check("submitting again is refused", r.status_code == 400, j2)
c = A.conn(); cur = c.cursor()
cur.execute("SELECT ReceivedBy FROM Assets WHERE _id=%s", [aid])
who = (cur.fetchone() or {}).get("ReceivedBy"); c.close()
check("the original signature was NOT overwritten", who == "Ancil Test", who)

print("\n5. Issuing a fresh link works, and retires the old one")
r = admin.get(f"/api/assets/{aid}/sign/link")
tok2 = (r.get_json() or {}).get("token") or ""
check("a new link is issued", bool(tok2) and tok2 != tok)
r = anon.get(f"/api/assets/sign/verify?token={tok2}")
check("the new link opens", (r.get_json() or {}).get("ok") is True,
      (r.get_json() or {}).get("error"))
r = anon.get(f"/api/assets/sign/verify?token={tok}")
j = r.get_json() or {}
check("the old link is now refused", j.get("ok") is False, j)
check("and says a newer one was issued", "newer one" in (j.get("error") or ""),
      j.get("error"))

print("\n6. A tampered or expired token is refused")
bad = tok2[:-2] + ("aa" if not tok2.endswith("aa") else "bb")
r = anon.get(f"/api/assets/sign/verify?token={bad}")
check("a tampered signature is rejected", (r.get_json() or {}).get("ok") is False)
expired = A._sign_token({"asset_id": aid, "name": "x", "n": nonce_on_asset()}, exp_hours=-1)
r = anon.get(f"/api/assets/sign/verify?token={expired}")
j = r.get_json() or {}
check("an expired token is rejected", j.get("ok") is False, j)
check("and is called expired", "expired" in (j.get("error") or ""), j.get("error"))

print("\n7. A link issued before any of this still works until it is signed")
legacy = A._sign_token({"asset_id": aid, "name": "legacy"}, exp_hours=24)
c = A.conn(); cur = c.cursor()
cur.execute("UPDATE Assets SET SignatureData='', SignNonce='', Status='Available', "
            "ReceivedBy='' WHERE _id=%s", [aid])
c.commit(); c.close()
r = anon.get(f"/api/assets/sign/verify?token={legacy}")
check("a nonce-less link opens while unsigned", (r.get_json() or {}).get("ok") is True,
      (r.get_json() or {}).get("error"))
r = anon.post("/api/assets/sign/approve",
              json={"token": legacy, "name": "Legacy Signer", "data": png()})
check("and can be signed once", (r.get_json() or {}).get("ok") is True,
      (r.get_json() or {}).get("error"))
r = anon.get(f"/api/assets/sign/verify?token={legacy}")
j = r.get_json() or {}
check("then it is refused too", j.get("ok") is False, j)
check("because the asset is already signed for",
      "already been signed" in (j.get("error") or ""), j.get("error"))

c = A.conn(); cur = c.cursor()
cur.execute("DELETE FROM Assets WHERE _id=%s", [aid])
c.commit(); c.close()
print("\n(test asset removed)")
print("\n" + ("ALL PASSED" if not fails else f"{len(fails)} FAILED: " + "; ".join(fails)))
raise SystemExit(1 if fails else 0)
