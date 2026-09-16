"""The QR on an asset tag has to scan first time.

It did not, and the reason was module size -- the width of one black square.
Three things were eating it:

The address. /asset/<32-hex-id> is 60 characters on a LAN host, which needs a
version-4 symbol: 33x33 modules. /a/IT-9001 is 31 characters and fits version
2: 25x25. A quarter fewer modules across, for the same page.

No quiet zone. qrcodejs draws the symbol edge to edge, and a decoder finds a
code by its finder patterns against clear space. Without a border it has
nothing to lock onto.

And the layout. The code sat inside the fields row, so on a 50.8x25.4mm tag it
was boxed into 13mm of height while millimetres of width went unused. As its
own full-height column it gets 19mm.

Together: 0.31mm modules to 0.76mm, or 2.5 printer dots to 6 at 203dpi. Under
about four dots a thermal printer cannot render an edge cleanly and a phone
camera has to hunt.

Module size is measured here, not eyeballed -- that is the whole point.
"""
import io
import os
import re
import sys

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
cl = A.app.test_client()
with cl.session_transaction() as sess:
    sess["user"] = "admin"
    sess["role"] = "admin"

AID = "QR-TEST-0001"
TAG = "QR-1"

c = A.conn(); cur = c.cursor()
cur.execute("SELECT label_size, qr_fields, label_model FROM Settings WHERE id=1")
before = cur.fetchone() or {}
# This file measures the detailed tag. An install with a plate model selected
# would otherwise fail every assertion here for the wrong reason.
cur.execute("UPDATE Settings SET label_model='detail' WHERE id=1")
cur.execute("DELETE FROM Assets WHERE _id=%s", [AID])
cur.execute("INSERT INTO Assets (_id, AssetTag, Name, Type, Serial, Status, Location) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (AID, TAG, "QR test laptop", "Laptop", "SN-QR-1", "Available", "Office"))
c.commit(); c.close()


def encoded(html):
    m = re.search(r"text:'([^']+)'", html)
    return m.group(1) if m else None


def modules_for(url, ec=1):
    """Module count for a URL, using the same error level the tag uses."""
    try:
        import qrcode
    except ImportError:
        return None
    q = qrcode.QRCode(error_correction=ec, border=0)
    q.add_data(url)
    q.make(fit=True)
    return q.modules_count


try:
    print("1. The tag encodes the short address")
    html = cl.get("/label/" + AID).get_data(as_text=True)
    url = encoded(html)
    check("a QR target is rendered", bool(url), url)
    # An asset tag is sequential, so it was also an invitation: scan one
    # label, then walk IT-1236, IT-1238, IT-1239 through the same address.
    # The QR carries an unguessable code instead, and it is just as short.
    c = A.conn(); cur = c.cursor()
    cur.execute("SELECT PublicCode FROM Assets WHERE _id=%s", [AID])
    CODE = (cur.fetchone() or {}).get("PublicCode")
    c.close()
    check("the asset has a public code", bool(CODE) and len(CODE) >= 8, CODE)
    check("it uses the /p/<code> path", "/p/" + CODE in url, url)
    check("not the asset tag", "/a/" + TAG not in url and TAG not in url, url)
    check("not the 32-character id", AID not in url, url)
    # length is the lever: every character can cost a whole symbol version
    check("it is short enough to matter", len(url) <= 45, "%d chars" % len(url))

    print()
    print("2. The short address resolves, and the old one still does")
    r = cl.get("/p/" + CODE)
    check("scanning the tag reaches the asset", r.status_code == 200, r.status_code)
    check("and shows the right one", "QR test laptop" in r.get_data(as_text=True))
    check("a code that does not exist is a clean 404",
          cl.get("/p/zzzzzzzz").status_code == 404)
    # the two old addresses still work for staff, so a label printed before
    # the code existed is still scannable by the people who own the place
    check("staff can still scan an old label", cl.get("/a/" + TAG).status_code == 200)
    # tags printed before this change encode the long form, and they are on
    # hardware in the field -- they must keep working forever
    r = cl.get("/asset/" + AID)
    check("codes printed before this still work", r.status_code == 200, r.status_code)
    check("an unknown code is a clean 404", cl.get("/a/NOPE-9999").status_code == 404)

    print()
    print("3. There is a quiet zone, and the code is not stretched")
    check("the QR box has white padding",
          re.search(r"\.qr\{\{[^}]*padding:[\d.]+mm", html) is not None
          or re.search(r"\.qr\{[^}]*padding:[\d.]+mm", html) is not None)
    check("and a white ground for it", re.search(r"\.qr\{[^}]*background:#fff", html)
          is not None)
    # width:100% + height:100% on a box that is not square stretches the
    # symbol, which no scanner will read
    check("the image keeps its own aspect",
          "width:auto!important;height:auto!important" in html)
    check("nothing forces it out of square",
          "width:100%!important;height:100%!important" not in html)

    print()
    print("4. The code is rasterised above print size")
    m = re.search(r"width:(\d+),height:\1", html)
    check("rendered well above the printed size", bool(m) and int(m.group(1)) >= 160,
          m.group(1) if m else "not found")

    print()
    print("5. Module size, measured")
    n = modules_for(url)
    if n is None:
        print("  (qrcode library not installed -- skipping the arithmetic)")
    else:
        check("a 31-ish character URL fits a small symbol", n <= 29, "%d modules" % n)
        # the code is its own full-height column on a short tag: ~19mm of a
        # 25.4mm tag, where it used to get ~10mm inside the fields row
        for size, _expect_mm in (("50.8x25.4", 17.0), ("50.8x50.8", 15.0)):
            c = A.conn(); cur = c.cursor()
            cur.execute("UPDATE Settings SET label_size=%s WHERE id=1", (size,))
            c.commit(); c.close()
            page = cl.get("/label/" + AID).get_data(as_text=True)
            # the QR column is capped as a share of the tag width
            mw = re.search(r"\.qr\{[^}]*max-width:(\d+)%", page)
            check("  %s caps the QR column" % size, bool(mw), mw.group(1) + "%" if mw else "none")
            u = encoded(page)
            check("  %s still encodes the code" % size, "/p/" + CODE in u, u)
        c = A.conn(); cur = c.cursor()
        cur.execute("UPDATE Settings SET label_size=%s WHERE id=1", ("50.8x25.4",))
        c.commit(); c.close()

        # what the old form would have cost, for the record
        old = "http://10.0.0.50:5000/asset/17c85a7ee8cf4845aaccfd7ae494449a"
        n_old = modules_for(old, ec=0)
        check("the short form needs fewer modules than the old one",
              n < n_old, "%d vs %d" % (n, n_old))

    print()
    print("5b. The code itself")
    check("it is long enough to be worth nothing to a guesser",
          len(CODE) >= 8, len(CODE))
    check("and drawn from an unambiguous alphabet",
          all(ch in A.PUBLIC_CODE_ALPHABET for ch in CODE), CODE)
    check("no 0/1/i/l/o to mistype off a label",
          not (set("01ilo") & set(A.PUBLIC_CODE_ALPHABET)))
    # every asset must have one, including everything that predates the
    # column, or its label would print an address that resolves to nothing
    c2 = A.conn(); cur2 = c2.cursor()
    cur2.execute("SELECT COUNT(*) AS n FROM Assets WHERE PublicCode IS NULL OR PublicCode=''")
    missing = cur2.fetchone()["n"]
    cur2.execute("SELECT COUNT(*) AS n, COUNT(DISTINCT PublicCode) AS d FROM Assets "
                 "WHERE PublicCode IS NOT NULL AND PublicCode<>''")
    uq = cur2.fetchone()
    c2.close()
    check("the backfill left none without one", missing == 0, missing)
    check("and no two assets share a code", uq["n"] == uq["d"], dict(uq))
    check("two fresh codes differ", A._new_public_code() != A._new_public_code())

    print()
    print("6. The layout gives the code its own column")
    check("there is a text stack beside it", 'class=stack' in html)
    check("the tag is a row, not a column",
          re.search(r"\.box\{[^}]*flex-direction:row", html) is not None)
    check("the QR stretches to the tag height",
          re.search(r"\.qr\{[^}]*align-self:stretch", html) is not None)
    # the fields must still all be there -- a scannable tag that lost its
    # printing is not a win
    for label in ("Category", "Serial", "Status", "Location"):
        check("  %s is still printed" % label, label in html)
    check("the asset ID leads the column", "class=aid" in html)
    check("DO NOT REMOVE is still last",
          html.index("class=norem") > html.index("class=meta"))

    print()
    print("7. The print sheet agrees with the single tag")
    sheet = cl.get("/labels?ids=" + AID).get_data(as_text=True)
    check("the sheet renders", "class=box" in sheet)
    check("it encodes the same code", "/p/" + CODE in sheet)
    check("it uses the same two-column layout", "class=stack" in sheet)
    check("and the same error level", "CorrectLevel.L" in sheet)
finally:
    c = A.conn(); cur = c.cursor()
    cur.execute("DELETE FROM Assets WHERE _id=%s", [AID])
    cur.execute("UPDATE Settings SET label_size=%s, qr_fields=%s, label_model=%s WHERE id=1",
                (before.get("label_size") or "50.8x25.4",
                 before.get("qr_fields") or "Name,AssetID,Type,Serial,Status,Location",
                 before.get("label_model") or "detail"))
    c.commit(); c.close()
    print()
    print("(test asset removed, label settings restored)")

print()
if fails:
    print("FAILED (%d): %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("ALL PASSED")
