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
cur.execute("SELECT label_size, qr_fields, label_model FROM Settings WHERE id=1")
before = cur.fetchone() or {}
# the detailed tag is what this file measures
cur.execute("UPDATE Settings SET label_model='detail' WHERE id=1")
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
        # The code is its own column now, so it is a sibling of the text
        # rather than something the notice follows. What still has to hold is
        # that the notice is the last thing in the text column.
        check("  the QR is a column beside the text", qr_i > rows_i)
        stack = html[html.index("class=stack"):html.index("class=qr")]
        check("  DO NOT REMOVE is last in the text column",
              stack.rindex("class=norem") > stack.rindex("class=meta"))

        # ---- the two identity lines appear exactly once -------------------
        # Counted in the markup only. The tag number also appears inside the
        # QR's target URL now (/a/<tag>), which is encoded into the image and
        # never printed as text.
        body = html[html.index("<body"):]
        # strip every script block, not just a trailing one: the QR library
        # tag sits before the markup, so slicing at the first <script> would
        # throw the whole tag away
        printed = re.sub(r"<script.*?</script>", "", body, flags=re.S)
        check("  the ID is printed once, not also as a field",
              printed.count(TAGNO) == 1, "%d occurrences" % printed.count(TAGNO))
        check("  the name is printed once on the tag",
              printed.count(NAME) == 1, "%d occurrences" % printed.count(NAME))
        check("  the notice still names the organisation and the instruction",
              "Do Not Remove" in html and "Property of" in html)

        # ---- the code is sized by the layout, not by arithmetic ----------
        # This used to reconstruct the millimetre budget and check it added
        # up. It no longer applies: the QR is its own full-height column, so
        # the browser derives its size from the tag rather than Python
        # estimating it -- which is the point, because every estimate here
        # was half a millimetre out and the bottom field paid for it.
        check("  the code is a column of its own",
              re.search(r"\.box\{[^}]*flex-direction:row", html) is not None)
        check("  and takes the height of the tag",
              re.search(r"\.qr\{[^}]*align-self:stretch", html) is not None)
        check("  capped so the text keeps its share of the width",
              re.search(r"\.qr\{[^}]*max-width:\d+%", html) is not None)
        check("  with a quiet zone around it",
              re.search(r"\.qr\{[^}]*padding:[\d.]+mm", html) is not None)

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
    # The floor moved from 1.25 to 1.1mm deliberately. A long organisation
    # name costs the head a second line, and the choice at that point is a
    # field printed small or a field not printed at all -- about 9 dots of cap
    # height at 203dpi, which a thermal printer does render.
    check("  but not below the legibility floor", bool(m) and float(m.group(1)) >= 1.1,
          m.group(1) + "mm" if m else "no rule")
    print()
    print("The organisation's name is not cut off")
    # It was: the brand was set at a fixed size with text-overflow:ellipsis,
    # inside the text column -- which is barely half the tag, because the QR
    # column beside it takes up to 46%. "NORTHSIDE SPORTS CLUB" printed as
    # "NORTHSIDE SP...". Shrinking to fit is right; cutting the owner's name off
    # their own property tag is not.
    c = A.conn(); cur = c.cursor()
    cur.execute("SELECT app_name FROM Settings WHERE id=1")
    _brand_before = (cur.fetchone() or {}).get("app_name") or "IT-Vault"
    LONG = "NORTHSIDE ATHLETIC SPORTS CLUB"
    cur.execute("UPDATE Settings SET app_name=%s WHERE id=1", [LONG])
    c.commit(); c.close()
    try:
        for size in ("50.8x25.4", "50.8x50.8"):
            html = page(size)
            body = html[html.index("<body"):]
            check("  %s prints the whole name" % size, LONG in body)
            m = re.search(r"\.brand\{[^}]*font-size:([\d.]+)mm", html)
            clamp = re.search(r"\.brand\{[^}]*line-clamp:(\d)", html)
            check("  %s sizes it to fit" % size, bool(m) and 1.5 <= float(m.group(1)) <= 3.0,
                  (m.group(1) + "mm") if m else "no rule")
            check("  %s allows a second line rather than cutting" % size,
                  bool(clamp) and clamp.group(1) == "2", clamp.group(1) if clamp else "none")
            check("  %s does not ellipsize the brand" % size,
                  re.search(r"\.brand\{[^}]*text-overflow", html) is None)
            # and the fields still print: the head taking a second line must
            # come out of the type size, not out of the asset's details
            check("  %s still prints every chosen field" % size,
                  html.count("class=kv") >= 3, html.count("class=kv"))
        # a short name keeps the full size
        c = A.conn(); cur = c.cursor()
        cur.execute("UPDATE Settings SET app_name='ACME' WHERE id=1"); c.commit(); c.close()
        m = re.search(r"\.brand\{[^}]*font-size:([\d.]+)mm", page("50.8x50.8"))
        check("  a short name is not shrunk", bool(m) and float(m.group(1)) >= 2.9,
              m.group(1) + "mm" if m else "no rule")
    finally:
        c = A.conn(); cur = c.cursor()
        cur.execute("UPDATE Settings SET app_name=%s WHERE id=1", [_brand_before])
        c.commit(); c.close()

finally:
    c = A.conn(); cur = c.cursor()
    cur.execute("DELETE FROM Assets WHERE _id=%s", (AID,))
    cur.execute("UPDATE Settings SET label_size=%s, qr_fields=%s, label_model=%s WHERE id=1",
                (before.get("label_size"), before.get("qr_fields"),
                 before.get("label_model") or "detail"))
    c.commit(); c.close()
    print()
    print("(test asset removed, label settings restored)")

print()
if fails:
    print("FAILED (%d): %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("ALL PASSED")
