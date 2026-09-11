"""The asset tag reads in a fixed order, and nothing falls off the bottom.

Requested order, top to bottom: brand name then the logo; the asset ID; the
asset name; the chosen fields; the QR beside them; and the DO NOT REMOVE strip
last. That strip is the reason the tag exists, so it is the one thing that must
never be the part that clips.

Fitting is the hard half. A 50.8x25.4mm tag has to hold a header, two identity
lines, four chosen fields and the notice, and the height budget was wrong three
ways at once: the header was costed at zero (it used not to exist on a compact
tag), only one flex gap was counted where there are now two, and the box border
sits outside the padding and was never counted at all. About 1.5mm of overrun,
which the bottom field paid for silently.
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


def read(*parts):
    # utf-8-sig: a file saved by a Windows editor carries a BOM
    return io.open(os.path.join(ROOT, *parts), encoding="utf-8-sig").read()


A.app.config["TESTING"] = True
cl = A.app.test_client()
with cl.session_transaction() as sess:
    sess["user"] = "admin"
    sess["role"] = "admin"

AID = "TAG-" + uuid.uuid4().hex[:6]
TAGNO = "TL-1"
NAME = "Tag layout laptop"

c = A.conn(); cur = c.cursor()
cur.execute("SELECT label_size, qr_fields FROM Settings WHERE id=1")
before = cur.fetchone() or {}
cur.execute("INSERT INTO Assets (_id, AssetTag, Name, Type, Serial, Status, Location) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (AID, TAGNO, NAME, "Laptop", "SN-TAG-1", "Available", "Office"))
c.commit(); c.close()


def page(label_size, fields="Name,AssetID,Type,Serial,Status,Location"):
    c = A.conn(); cur = c.cursor()
    cur.execute("UPDATE Settings SET label_size=%s, qr_fields=%s WHERE id=1",
                (label_size, fields))
    c.commit(); c.close()
    r = cl.get("/label/" + AID)
    assert r.status_code == 200, r.status_code
    return r.get_data(as_text=True)


try:
    for size, kind in (("50.8x25.4", "compact"), ("50.8x50.8", "full")):
        print("%s tag (%s)" % (size, kind))
        html = page(size)

        # ---- order, read straight off the markup -------------------------
        brand_i = html.index("class=brand")
        logo_i = html.find("class=logo src")
        aid_i = html.index("class=aid")
        name_i = html.index("class=name")
        rows_i = min([i for i in (html.find("class=kv"), html.find("class=k>"))
                      if i != -1] or [10 ** 9])
        qr_i = html.index("id=qr")
        norem_i = html.index("class=norem")

        check("  the logo comes after the brand name", logo_i > brand_i,
              "brand@%d logo@%d" % (brand_i, logo_i))
        check("  the asset ID comes next", aid_i > brand_i)
        check("  the asset name is below the ID", name_i > aid_i,
              "aid@%d name@%d" % (aid_i, name_i))
        check("  the chosen fields follow the name", rows_i > name_i,
              "name@%d rows@%d" % (name_i, rows_i))
        check("  the QR sits after them, in the same row", qr_i > rows_i)
        check("  DO NOT REMOVE is last", norem_i > qr_i)

        # ---- the two identity lines appear exactly once -------------------
        check("  the ID is printed once, not also as a field",
              html.count(TAGNO) == 1, "%d occurrences" % html.count(TAGNO))
        # the name appears in <title> too, so twice in the document
        body = html[html.index("<body"):]
        check("  the name is printed once on the tag",
              body.count(NAME) == 1, "%d occurrences" % body.count(NAME))
        check("  the notice still names the organisation and the instruction",
              "Do Not Remove" in html and "Property of" in html)

        # ---- the budget adds up ------------------------------------------
        lh = float(size.split("x")[1])
        pads = [float(x) for x in re.findall(r"padding:([\d.]+)mm", html)]
        pad = pads[0] if pads else 0.0
        gap = float(re.search(r"gap:([\d.]+)mm", html).group(1))
        qr_px = int(re.search(r"width:(\d+)px;height:\1px", html).group(1))
        qr_mm = qr_px / 3.78
        # header + notice + QR row + padding + two gaps + border must fit
        head_mm = 4.2 if lh < 35.0 else 5.8
        norem_mm = 2.8 if lh < 35.0 else 5.2
        total = pad * 2 + head_mm + norem_mm + gap * 2 + 0.55 + qr_mm
        check("  the QR and everything around it fit the tag height",
              total <= lh + 0.1, "needs %.2fmm of %.1fmm" % (total, lh))
        check("  the QR is not wider than its column",
              qr_mm <= float(size.split("x")[0]) * 0.45,
              "%.1fmm on a %smm tag" % (qr_mm, size.split("x")[0]))

        # ---- the row style adapts rather than overflowing -----------------
        check("  rows are sized from the space left, not a fixed guess",
              "max-height:" in html and "flex:1 1 auto" in html)
        print()

    print("The asset name is a choice, not furniture")
    # It was rendered unconditionally -- first in the header, then at the top
    # of the column -- so unticking it in Settings did nothing at all.
    off = page("50.8x25.4", "AssetID,Type,Serial,Status")
    off_body = off[off.index("<body"):]
    check("  unticked: no name element", "class=name" not in off_body)
    check("  unticked: the name is nowhere on the tag", NAME not in off_body)
    check("  unticked: the ID is still there", TAGNO in off_body)
    on = page("50.8x25.4", "Name,AssetID,Type,Serial,Status")
    on_body = on[on.index("<body"):]
    check("  ticked: the name is back", NAME in on_body)
    # the space it would have used goes to the fields, not to nothing
    m_off = re.search(r"\.kv\{font-size:([\d.]+)mm", off)
    m_on = re.search(r"\.kv\{font-size:([\d.]+)mm", on)
    check("  unticked: the fields get the freed space",
          bool(m_off) and bool(m_on) and float(m_off.group(1)) >= float(m_on.group(1)),
          "%s vs %s" % (m_off.group(1) if m_off else "?", m_on.group(1) if m_on else "?"))

    print()
    print("The sidebar shows Logo Text, not the organisation name")
    # Two separate settings, and the field is labelled "Logo Text (sidebar)".
    # applyBranding read app_name for both, so the sidebar always showed the
    # company name and the setting appeared to do nothing.
    appjs = read("app.js")
    check("  the sidebar is set from logo_text",
          "me.logo_text" in appjs, "no reference to me.logo_text")
    check("  it falls back to the app name when blank",
          "(me.logo_text||'').trim()||nm" in appjs)
    check("  the browser tab still uses the organisation name",
          "document.title=nm+' // Assets Manager'" in appjs)
    check("  nothing still assigns the app name to the sidebar",
          not re.search(r"sideName'\)\.textContent=nm;", appjs)
          and not re.search(r"st\.textContent=nm;", appjs))
    check("  the server supplies it", '"logo_text": s.get("logo_text"' in read("app.py"))

    print()
    print("Every chosen field is printed, even when there are many")
    html = page("50.8x25.4", "Name,AssetID,Type,Serial,Status,Location,Department,Warranty")
    for label in ("Category", "Serial", "Status", "Location", "Warranty"):
        check("  %s is on the tag" % label, label in html)
    m = re.search(r"\.kv\{font-size:([\d.]+)mm", html)
    check("  and the type shrank to make room", bool(m) and float(m.group(1)) < 2.05,
          m.group(1) + "mm" if m else "no rule")
    check("  but not below the legibility floor", bool(m) and float(m.group(1)) >= 1.25,
          m.group(1) + "mm" if m else "no rule")
finally:
    c = A.conn(); cur = c.cursor()
    cur.execute("DELETE FROM Assets WHERE _id=%s", (AID,))
    cur.execute("UPDATE Settings SET label_size=%s, qr_fields=%s WHERE id=1",
                (before.get("label_size"), before.get("qr_fields")))
    c.commit(); c.close()
    print()
    print("(test asset removed, label settings restored)")

print()
if fails:
    print("FAILED (%d): %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("ALL PASSED")
