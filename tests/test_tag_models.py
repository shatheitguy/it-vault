"""Two shapes of asset tag, because they answer different questions.

"Detailed" is the tag this app has always printed: brand, asset ID, name, the
fields chosen in Settings, and the DO NOT REMOVE notice. It is for an IT team
reading a label off a shelf.

"Plate" is the engraved-plate convention every asset register in the world
uses -- the code on the left, and the owner's mark, one caption and one big
number on the right. Nothing else. It is for identifying a thing across a
room. The four captions offered (Asset No., Council Asset, Product ID Code,
Tracked Asset) are what the plates in circulation actually say; the caption is
free text because the fifth organisation will call it something else again.

The two are checked against each other here, because the easy way to get this
wrong is to let the plate quietly inherit a piece of the detailed tag -- a
border, a field row, the notice strip -- and only find out on a printer.
"""
import io
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
cl = A.app.test_client()
with cl.session_transaction() as sess:
    sess["user"] = "admin"
    sess["role"] = "admin"

AID = "TM-" + uuid.uuid4().hex[:8]
TAG = "45464544"
NAME = "Boardroom projector"
SERIAL = "SN-TM-1"

c = A.conn(); cur = c.cursor()
cur.execute("SELECT label_model, label_caption, label_size FROM Settings WHERE id=1")
before = cur.fetchone() or {}
cur.execute("INSERT INTO Assets (_id, AssetTag, Name, Type, Serial, Status, Location) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (AID, TAG, NAME, "Projector", SERIAL, "Available", "Head Office"))
c.commit(); c.close()
CODE = A._asset_public_code(AID)


def label(model=None, caption=None, size=None):
    body = {}
    if model is not None:
        body["label_model"] = model
    if caption is not None:
        body["label_caption"] = caption
    if size is not None:
        body["label_size"] = size
    if body:
        r = cl.put("/api/settings", json=body)
        assert r.status_code == 200, r.status_code
    return cl.get("/label/" + AID).get_data(as_text=True)


try:
    print("1. The model is a setting, and it defaults to what was there before")
    s = cl.get("/api/settings").get_json()
    check("the page is told the model", "label_model" in s and "label_caption" in s)
    check("only two models exist", A.LABEL_MODELS == ("detail", "plate"), A.LABEL_MODELS)
    check("the four captions are offered",
          set(A.LABEL_CAPTION_PRESETS) ==
          {"Asset No.", "Council Asset", "Product ID Code", "Tracked Asset"},
          A.LABEL_CAPTION_PRESETS)
    # an install that never opens the setting must keep the tag it has
    cl.put("/api/settings", json={"label_model": "nonsense"})
    check("an unknown model falls back to detailed",
          cl.get("/api/settings").get_json()["label_model"] == "detail")

    print()
    print("2. Detailed prints what it always did")
    html = label("detail", size="50.8x25.4")
    check("  the brand header is there", "class=brand" in html)
    check("  the chosen fields print", "class=kv" in html)
    check("  the notice strip is there", "class=norem" in html and "Do Not Remove" in html)
    check("  and it is a bordered box", "class=box" in html and "border:1px solid" in html)
    check("  no plate markup leaked in", "class=plate" not in html)

    print()
    print("3. Plate prints a plate")
    html = label("plate", "Asset No.")
    check("  the plate layout is used", "class=plate" in html)
    check("  the code is a square column", re.search(r"\.pqr\{[^}]*width:[\d.]+mm", html) is not None)
    check("  the caption prints", ">Asset No.<" in html)
    check("  the asset number is the headline", re.search(r"class=pid[^>]*>%s<" % TAG, html) is not None)
    # everything the detailed tag carries and a plate does not
    for gone, why in (("class=kv", "a field row"), ("class=norem", "the notice"),
                      ("class=brand", "the brand strip"), ("class=stack", "the text column")):
        check("  no %s on a plate" % why, gone not in html)
    check("  the asset name is not on it", NAME not in html.split("<title>")[1].split("</title>")[1])
    check("  nor the serial", SERIAL not in html)
    # the photographed plates are cut metal; a printed rule around the edge
    # only makes the alignment look wrong
    check("  and no border is drawn", "border:1px solid #222" not in html)

    print()
    print("4. Every one of the four captions prints as asked")
    for cap in A.LABEL_CAPTION_PRESETS:
        html = label("plate", cap)
        m = re.search(r"class=pcap>([^<]*)<", html)
        check("  %-16s prints" % cap, bool(m) and m.group(1) == cap, m.group(1) if m else "none")
    # free text, because the next organisation calls it something else
    html = label("plate", "Equipment Ref")
    check("  a caption of their own works too", ">Equipment Ref<" in html)
    long_cap = "X" * 80
    cl.put("/api/settings", json={"label_caption": long_cap})
    stored = cl.get("/api/settings").get_json()["label_caption"]
    check("  and an absurd one is capped, not rejected", len(stored) <= 40, len(stored))

    print()
    print("5. The QR is the same address either way")
    for model in ("detail", "plate"):
        html = label(model, "Asset No.")
        m = re.search(r"text:'([^']+)'", html)
        check("  %-6s encodes the public code" % model,
              bool(m) and ("/p/" + CODE) in m.group(1), m.group(1) if m else "none")
    check("  which means a plate scan reaches the same page",
          cl.get("/p/" + CODE).status_code == 200)

    print()
    print("6. A sheet of plates is the same tag, many times")
    sheet = cl.get("/labels?ids=" + AID).get_data(as_text=True)
    check("  the sheet uses the model too", "class=plate" in sheet)
    check("  one plate per asset", sheet.count("class=plate") == 1, sheet.count("class=plate"))
    check("  and the same code", ("/p/" + CODE) in sheet)

    print()
    print("7. It fits the stock, both sizes")
    for size, want_w, want_h in (("50.8x25.4", 50.8, 25.4), ("50.8x50.8", 50.8, 50.8)):
        html = label("plate", "Asset No.", size=size)
        m = re.search(r"\.plate\{width:([\d.]+)mm;height:([\d.]+)mm", html)
        check("  %s renders at its stock size" % size,
              bool(m) and float(m.group(1)) == want_w and float(m.group(2)) == want_h,
              (m.group(1) + "x" + m.group(2)) if m else "no rule")
        # a number that runs off the plate is not a number
        idm = re.search(r"class=pid style=\"font-size:([\d.]+)mm\"", html)
        check("  %s sizes the number to fit" % size,
              bool(idm) and 1.6 <= float(idm.group(1)) <= 6.4,
              idm.group(1) + "mm" if idm else "none")
    # a long asset tag must shrink rather than overflow
    c2 = A.conn(); cur2 = c2.cursor()
    cur2.execute("UPDATE Assets SET AssetTag=%s WHERE _id=%s", ["IT-2026-CORP-0001234", AID])
    c2.commit(); c2.close()
    html = label("plate", "Asset No.", size="50.8x25.4")
    long_id = re.search(r"class=pid style=\"font-size:([\d.]+)mm\"", html)
    check("  a long asset number is shrunk to fit",
          bool(long_id) and float(long_id.group(1)) < 4.6, long_id.group(1) if long_id else "none")
    check("  and printed whole", "IT-2026-CORP-0001234" in html)
    c2 = A.conn(); cur2 = c2.cursor()
    cur2.execute("UPDATE Assets SET AssetTag=%s WHERE _id=%s", [TAG, AID])
    c2.commit(); c2.close()

    print()
    print("8. The picker is wired to it")
    html_idx = read("index.html")
    js = read("app.js")
    css = read("style.css")
    check("there is a model grid", 'id="tagModelGrid"' in html_idx)
    for cap in A.LABEL_CAPTION_PRESETS:
        check("  %-16s is offered as a card" % cap, 'data-caption="%s"' % cap in html_idx)
    check("the detailed model is offered too", 'data-model="detail"' in html_idx)
    check("each card shows a drawing of its tag", ".tm-prev{" in css and "tm-qr" in html_idx)
    check("the caption is editable", 'id="label_caption"' in html_idx)
    check("the save sends both", "label_model: TAG_MODEL" in js and "label_caption:" in js)
    # field checkboxes do nothing on a plate, so they are put away rather
    # than left sitting there looking connected
    check("the field list hides for a plate",
          "labelFieldsPanel" in js and 'id="labelFieldsPanel"' in html_idx)
finally:
    c = A.conn(); cur = c.cursor()
    cur.execute("DELETE FROM Assets WHERE _id=%s", [AID])
    cur.execute("UPDATE Settings SET label_model=%s, label_caption=%s, label_size=%s WHERE id=1",
                (before.get("label_model") or "detail",
                 before.get("label_caption") or "Asset No.",
                 before.get("label_size") or "50.8x25.4"))
    c.commit(); c.close()
    print()
    print("(test asset removed, label settings restored)")

print()
if fails:
    print("FAILED (%d): %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("ALL PASSED")
