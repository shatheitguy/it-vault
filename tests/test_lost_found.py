"""A scanned tag tells a stranger who owns the thing -- and nothing else.

The QR on an asset label is, by design, readable by anyone holding the asset:
a courier, a cleaner, whoever picks a laptop up off a train seat. That page
used to print the serial number, the status, who it is assigned to, that
person's department, designation and email address, and the purchase date.
All of it to anyone who pointed a camera at a sticker.

What a finder actually needs is two things -- who it belongs to and how to
reach them -- plus a way to say "I have it" without having to ring anyone.
That is what the page is now, and the report that comes back is the point:
a name and a number, mailed straight to whoever the asset is assigned to.

Signed in, it is still the full record. Scanning a tag to see what an asset
is remains the reason IT scans tags.
"""
import io
import json
import os
import re
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


def read(name):
    return io.open(os.path.join(ROOT, name), encoding="utf-8-sig").read()


A.app.config["TESTING"] = True
anon = A.app.test_client()
staff = A.app.test_client()
with staff.session_transaction() as sess:
    sess["user"] = "admin"
    sess["role"] = "admin"

AID = "LFT-" + uuid.uuid4().hex[:8]
TAG = "LFT-9001"
SERIAL = "SN-LOSTFOUND-1"
NAME = "Boardroom projector"

c = A.conn(); cur = c.cursor()
cur.execute("SELECT company_phone, app_name FROM Settings WHERE id=1")
before = cur.fetchone() or {}
cur.execute("UPDATE Settings SET company_phone=%s WHERE id=1", ["+971 4 555 0000"])
cur.execute("INSERT INTO Assets (_id, AssetTag, Name, Type, Serial, Status, Location, "
            "PurchaseDate, Price) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (AID, TAG, NAME, "Projector", SERIAL, "Available", "Head Office",
             "2026-01-15", 4800))
c.commit(); c.close()

sent = []


def fake_send(subject, body, kind=None):
    sent.append({"subject": subject, "body": body, "kind": kind})
    return True


try:
    print("1. A stranger who scans the tag learns who owns it, and no more")
    A._PUBLIC_HITS.clear()
    # inserted by SQL above, so mint the code the way a real creation does
    CODE = A._asset_public_code(AID)
    r = anon.get("/p/" + CODE)
    check("the tag resolves", r.status_code == 200, r.status_code)
    page = r.get_data(as_text=True)
    for leak in (SERIAL, NAME, "Head Office", "4800", "2026-01-15",
                 "Assigned To", "Department", "Designation", "Signature", "Serial"):
        check("  does not print %r" % leak, leak not in page)
    # the tab title lands in browser history, so it leaks too
    title = re.search(r"<title>(.*?)</title>", page).group(1)
    check("  the tab title gives nothing away", NAME not in title and SERIAL not in title, title)
    check("  it says whose property it is", "Property of" in page)
    check("  it shows the contact number", "+971 4 555 0000" in page)
    check("  the number is tap-to-dial", 'href="tel:+97145550000"' in page)
    check("  the asset tag is shown (it is printed on the label anyway)", TAG in page)
    check("  there is a way to report it", "lfOpen" in page and "REPORT TO LOST" in page.upper())
    check("  and no link into the app", "Open Printable Tag" not in page)
    # a card explaining what it is not deliberately withholding reads as
    # evasive, and nobody holding a found laptop cares
    check("  it does not narrate its own privacy",
          "Nothing about this item" not in page and "go only to" not in page)
    # the owner's name is the headline; a strip above repeating it was noise
    check("  the owner name is not printed twice",
          page.count(">" + "IT-Vault" + "<") <= 2, page.count(">IT-Vault<"))
    check("  and it is laid out as a card, not a form",
          "pubcard" in page and "class=powner" in page)

    print()
    print("1b. A tag is not an address: the sequence cannot be walked")
    # This is the whole reason for the code. Anyone holding one label knows
    # the format of every other one.
    check("  the asset tag is not a public address",
          anon.get("/a/" + TAG).status_code == 404, anon.get("/a/" + TAG).status_code)
    check("  nor is the internal id",
          anon.get("/asset/" + AID).status_code == 404)
    check("  and a guessed code says nothing",
          anon.get("/p/zzzzzzzz").status_code == 404)
    check("  the code is not derived from the tag",
          TAG.lower().replace("-", "") not in CODE.lower(), CODE)

    print()
    print("2. Signed in, the same address is still the full record")
    sp = staff.get("/p/" + CODE).get_data(as_text=True)
    check("  staff see the serial", SERIAL in sp)
    check("  staff see the name", NAME in sp)
    check("  staff see the detail table", "Assigned To" in sp)
    check("  staff do not get the finder form", "lfOpen" not in sp)

    print()
    print("3. The report a finder sends")
    A._PUBLIC_HITS.clear()
    real_send, A.send_notification = A.send_notification, fake_send
    r = anon.post("/api/public/lostfound", json={
        "code": CODE, "name": "Ravi Kumar", "mobile": "+971 55 987 6543",
        "note": "Left on the 8am bus"})
    j = r.get_json()
    check("  it is accepted", r.status_code == 200 and j.get("ok"), j)
    check("  and answers with a reference", str(j.get("ref", "")).startswith("LF-"), j.get("ref"))
    check("  nothing about the asset comes back",
          NAME not in json.dumps(j) and SERIAL not in json.dumps(j), j)
    rid = int(str(j["ref"]).split("-")[1])

    print()
    print("4. Which reaches the people who can do something about it")
    check("  a notification went out", len(sent) == 1, sent)
    if sent:
        msg = sent[0]
        check("  tagged as a lost & found report", msg["kind"] == "lostfound.found", msg["kind"])
        check("  carrying the finder's name", "Ravi Kumar" in msg["body"])
        check("  and their number -- the whole point", "+971 55 987 6543" in msg["body"])
        check("  and where they found it", "Left on the 8am bus" in msg["body"])
        check("  naming the asset, for the people who are allowed to know",
              TAG in msg["subject"] or TAG in msg["body"])

    print()
    print("5. What the endpoint refuses")
    A._PUBLIC_HITS.clear()
    r = anon.post("/api/public/lostfound", json={"code": CODE, "name": "", "mobile": ""})
    check("  no name or number", r.status_code == 400, r.status_code)
    r = anon.post("/api/public/lostfound", json={"code": "zzzzzzzz", "name": "X", "mobile": "1"})
    check("  a code that does not exist", r.status_code == 404, r.status_code)
    # filing against a tag would hand back the sequence the QR stopped giving
    r = anon.post("/api/public/lostfound", json={"code": TAG, "name": "X", "mobile": "1"})
    check("  an asset tag is refused here too", r.status_code == 404, r.status_code)
    r = anon.post("/api/public/lostfound", json={"asset": CODE, "name": "X", "mobile": "1"})
    check("  and the old field name buys nothing", r.status_code in (400, 404), r.status_code)
    # a public endpoint with no account behind it needs a ceiling
    A._PUBLIC_HITS.clear()
    codes = [anon.post("/api/public/lostfound",
                       json={"code": CODE, "name": "Flood", "mobile": "1"}).status_code
             for _ in range(7)]
    check("  the first few get through", codes[:5] == [200] * 5, codes)
    check("  then it throttles", codes[5] == 429 and codes[6] == 429, codes)
    A._PUBLIC_HITS.clear()
    # length caps, so a public form cannot be used to write an essay into the db
    long_name = "N" * 400
    r = anon.post("/api/public/lostfound", json={"code": CODE, "name": long_name,
                                                 "mobile": "5" * 200, "note": "z" * 5000})
    check("  an oversized submission is stored, truncated", r.status_code == 200, r.status_code)
    cc = A.conn(); ccur = cc.cursor()
    ccur.execute("SELECT finder_name, finder_mobile, finder_note FROM LostFound "
                 "WHERE asset_id=%s ORDER BY id DESC LIMIT 1", [AID])
    big = ccur.fetchone(); cc.close()
    check("  name capped", len(big["finder_name"]) <= 120, len(big["finder_name"]))
    check("  mobile capped", len(big["finder_mobile"]) <= 40, len(big["finder_mobile"]))
    check("  note capped", len(big["finder_note"]) <= 500, len(big["finder_note"]))
    A.send_notification = real_send

    print()
    print("6. The report shows up where staff will see it")
    r = staff.get("/api/lostfound")
    check("  the list loads", r.status_code == 200, r.status_code)
    rows = r.get_json()
    mine = [x for x in rows if x.get("asset_id") == AID]
    check("  the report is in it", len(mine) >= 1, len(mine))
    one = [x for x in mine if x["id"] == rid][0]
    check("  with the finder's name", one["finder_name"] == "Ravi Kumar")
    check("  and number", one["finder_mobile"] == "+971 55 987 6543")
    check("  joined to the asset it belongs to", one["asset_name"] == NAME)
    # a stranger telling you they have it IS the found state; there is
    # nothing to triage before that is true
    check("  a finder's report lands as found", one["status"] == "found", one["status"])
    # the address is kept for abuse, and is nobody's business on a web page
    check("  the reporter's IP is not handed to the browser", "reporter_ip" not in one, one.keys())
    check("  signing out closes the list", anon.get("/api/lostfound").status_code in (401, 403),
          anon.get("/api/lostfound").status_code)

    print()
    print("7. Status is a decision, and the asset follows it")
    r = staff.patch("/api/lostfound/%d" % rid, json={"status": "lost"})
    check("  a report can be marked lost", r.status_code == 200, r.get_json())
    cc = A.conn(); ccur = cc.cursor()
    ccur.execute("SELECT Status FROM Assets WHERE _id=%s", [AID])
    check("  and the asset is marked Lost/Stolen",
          ccur.fetchone()["Status"] == "Lost/Stolen")
    cc.close()
    r = staff.patch("/api/lostfound/%d" % rid, json={"status": "returned"})
    cc = A.conn(); ccur = cc.cursor()
    ccur.execute("SELECT Status FROM Assets WHERE _id=%s", [AID])
    check("  getting it back puts the asset into the pool",
          ccur.fetchone()["Status"] == "Available")
    # returning must never overwrite a status somebody else set deliberately
    ccur.execute("UPDATE Assets SET Status='Checked-Out' WHERE _id=%s", [AID])
    cc.commit(); cc.close()
    staff.patch("/api/lostfound/%d" % rid, json={"status": "returned"})
    cc = A.conn(); ccur = cc.cursor()
    ccur.execute("SELECT Status FROM Assets WHERE _id=%s", [AID])
    check("  but only from Lost/Stolen -- Checked-Out is left alone",
          ccur.fetchone()["Status"] == "Checked-Out")
    ccur.execute("UPDATE Assets SET Status='Available' WHERE _id=%s", [AID])
    cc.commit(); cc.close()
    check("  an invented status is refused",
          staff.patch("/api/lostfound/%d" % rid, json={"status": "banana"}).status_code == 400)
    # five statuses said less than three: open and closed carried no fact a
    # date did not already carry
    check("  there are exactly three", A.LOSTFOUND_STATUSES == ["lost", "found", "returned"],
          A.LOSTFOUND_STATUSES)
    for gone in ("open", "closed"):
        check("  %-6s is no longer offered" % gone,
              staff.patch("/api/lostfound/%d" % rid, json={"status": gone}).status_code == 400)
    check("  and a visitor cannot change one",
          anon.patch("/api/lostfound/%d" % rid, json={"status": "closed"}).status_code in (401, 403))

    print()
    print("8. Staff can log something missing before anyone finds it")
    r = staff.post("/api/lostfound", json={"asset": TAG, "note": "not in the meeting room"})
    j = r.get_json()
    check("  it is logged", r.status_code == 200 and j.get("ok"), j)
    lost_id = j["id"]
    cc = A.conn(); ccur = cc.cursor()
    ccur.execute("SELECT Status FROM Assets WHERE _id=%s", [AID])
    check("  and the asset is marked lost straight away",
          ccur.fetchone()["Status"] == "Lost/Stolen")
    cc.close()
    row = [x for x in staff.get("/api/lostfound").get_json() if x["id"] == lost_id][0]
    check("  recorded as staff-logged, not a finder's report", row["kind"] == "lost", row["kind"])
    check("  deleting a report works",
          staff.delete("/api/lostfound/%d" % lost_id).status_code == 200)
    check("  and it is gone",
          not [x for x in staff.get("/api/lostfound").get_json() if x["id"] == lost_id])

    print()
    print("9. Notifications: one list, and it is actually consulted")
    s = staff.get("/api/settings").get_json()
    check("  the page is told what can be sent", len(s.get("notify_catalog") or []) >= 12,
          len(s.get("notify_catalog") or []))
    check("  including the lost & found report", "lostfound.found" in
          [t["key"] for t in s["notify_catalog"]])
    check("  everything is on until someone says otherwise",
          all(s["notify_types"].get(k["key"]) for k in s["notify_catalog"]))
    staff.put("/api/settings", json={"notify_types": {"asset.created": False,
                                                      "made.up.key": True}})
    s2 = staff.get("/api/settings").get_json()
    check("  a type can be switched off", s2["notify_types"]["asset.created"] is False)
    check("  the column it replaced is kept in step", not s2["notify_new"], s2["notify_new"])
    check("  an unknown key is ignored, not stored", "made.up.key" not in s2["notify_types"])
    check("  and the others are untouched", s2["notify_types"]["heartbeat.down"] is True)
    # the gate is the point: a switched-off type must not reach any channel
    reached = []
    real_all, A._hb_all_channels = A._hb_all_channels, lambda: (reached.append(1) or [])
    off = A.send_notification("should not go", "body", kind="asset.created")
    looked_up_when_off = len(reached)
    A.send_notification("should go", "body", kind="heartbeat.down")
    looked_up_when_on = len(reached)
    A._hb_all_channels = real_all
    check("  a disabled type returns without sending", off is False)
    check("  and never even looks up the channels", looked_up_when_off == 0, looked_up_when_off)
    check("  while an enabled one does", looked_up_when_on == 1, looked_up_when_on)
    staff.put("/api/settings", json={"notify_types": {k["key"]: True
                                                      for k in s["notify_catalog"]}})
    check("  everything restored",
          all(staff.get("/api/settings").get_json()["notify_types"].values()))

    print()
    print("10. It is in the backup, and in the page")
    cc = A.conn(); ccur = cc.cursor()
    tables = [t.lower() for t in A._backup_tables(ccur, "all")]
    cc.close()
    check("  LostFound is backed up", "lostfound" in tables, tables[-6:])
    html = read("index.html")
    js = read("app.js")
    check("  the sidebar has an entry", 'id="navLostFound"' in html)
    check("  which is permission-gated", "canDo('assets.lostfound')" in js)
    check("  the page exists", 'id="page-lostfound"' in html)
    check("  and is routed", "'page-lostfound'" in js and "loadLostFound()" in js)
    check("  notifications read SMTP, then channels, then what to send",
          html.index("EMAIL NOTIFICATIONS (SMTP)") < html.index("NOTIFICATION CHANNELS")
          < html.index("WHAT TO SEND"))
    check("  the old scattered toggles are gone",
          'id="uNew"' not in html and 'id="notify_on_create"' not in html)
    css = read("style.css")
    # both sides stripped of spaces, or the needle never matches the haystack
    check("  reporting an asset lost is a form, not a browser prompt",
          'id="lostModal"' in html and 'id="lm_asset"' in html)
    check("  with no prompt() left in the flow",
          "prompt('Asset ID" not in js and "prompt(\"Asset ID" not in js)
    check("  the report table becomes cards on a phone",
          "#lfGridthead{display:none}" in css.replace(" ", ""))
finally:
    c = A.conn(); cur = c.cursor()
    cur.execute("DELETE FROM LostFound WHERE asset_id=%s", [AID])
    cur.execute("DELETE FROM Assets WHERE _id=%s", [AID])
    cur.execute("UPDATE Settings SET company_phone=%s WHERE id=1",
                [before.get("company_phone") or ""])
    c.commit(); c.close()
    print()
    print("(test asset, reports and contact number cleaned up)")

print()
if fails:
    print("FAILED (%d): %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("ALL PASSED")
