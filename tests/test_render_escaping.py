"""Markup typed into a field stays text on every page that prints it.

The public asset page and the two label pages built their HTML with f-strings
straight out of the database:

    rows_html = "".join(f"<tr><td class='v'>{v}</td></tr>" ...)

So an asset called `<script>...</script>` ran in the browser of whoever opened
the tag — and the address of that page is printed on every QR label the system
produces. Nor did it need a staff account to plant: `EmployeeName`,
`Department` and `Designation` arrive from Active Directory, and the settings
strings (organisation name, label caption, contact number) print on every tag.

This drives the real routes with a hostile asset and reads what comes back.
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


A.app.config["TESTING"] = True

# The payload is deliberately boring: a script tag, an event handler and an
# attribute break. If any of the three survives as markup, the page is
# executing what somebody typed.
PAYLOAD = "<script>alert(1)</script>"
ATTR_BREAK = '" onmouseover="alert(2)'
IMG = "<img src=x onerror=alert(3)>"

AID = "xss-" + uuid.uuid4().hex[:8]
TAG = "XSS-" + uuid.uuid4().hex[:4].upper()

c = A.conn(); cur = c.cursor()
cur.execute("""INSERT INTO Assets (_id, AssetTag, Name, Type, Status, Serial, Location, Note)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (AID, TAG, "Laptop " + PAYLOAD, "Laptop", "Available",
             "SN" + ATTR_BREAK, IMG, "note " + PAYLOAD))
c.commit(); c.close()

# the settings a tag prints, saved so they can be put back
c = A.conn(); cur = c.cursor()
cur.execute("SELECT app_name, label_caption, company_phone FROM Settings WHERE id=1")
BEFORE = cur.fetchone() or {}
c.close()


def set_settings(app_name, caption, phone):
    c = A.conn(); cur = c.cursor()
    cur.execute("UPDATE Settings SET app_name=%s, label_caption=%s, company_phone=%s WHERE id=1",
                (app_name, caption, phone))
    c.commit(); c.close()


def clean(html, label):
    """Nothing hostile survived as markup."""
    bad = []
    if "<script>alert(1)</script>" in html:
        bad.append("<script> executes")
    if "onerror=alert(3)" in html and "&lt;img" not in html:
        bad.append("<img onerror> executes")
    if 'onmouseover="alert(2)"' in html:
        bad.append("attribute break")
    check(label, not bad, bad)


staff = A.app.test_client()
with staff.session_transaction() as s:
    s["user"] = "admin"
    s["role"] = "admin"

try:
    print()
    print("1. The page every QR label points at")
    r = staff.get("/asset/" + AID)
    html = r.get_data(as_text=True)
    check("the signed-in view renders", r.status_code == 200, r.status_code)
    clean(html, "nothing from the asset executes")
    check("the name is still shown, as text",
          "&lt;script&gt;" in html, "escaped, not stripped -- the value is still readable")
    check("and the attribute break is neutralised",
          "&quot;" in html or "&#34;" in html, "the serial carried a quote")

    print()
    print("2. The same page as a stranger sees it")
    anon = A.app.test_client()
    code = A._asset_public_code(AID)
    r2 = anon.get("/p/" + code) if code else None
    if r2 is not None:
        html2 = r2.get_data(as_text=True)
        check("the public card renders", r2.status_code == 200, r2.status_code)
        clean(html2, "nothing from the asset executes there either")
        check("and it still refuses to print the serial",
              "SN" + ATTR_BREAK not in html2 and "SN&quot;" not in html2,
              "the public card was never meant to carry it")

    print()
    print("3. A single printed label")
    r3 = staff.get("/label/" + AID)
    html3 = r3.get_data(as_text=True)
    check("the label renders", r3.status_code == 200, r3.status_code)
    clean(html3, "nothing from the asset executes on a label")

    print()
    print("4. A print sheet")
    r4 = staff.get("/labels?ids=" + AID)
    html4 = r4.get_data(as_text=True)
    check("the sheet renders", r4.status_code == 200, r4.status_code)
    clean(html4, "nothing from the asset executes on a sheet")

    print()
    print("5. The settings printed on every tag")
    # organisation name, caption and phone are typed in Settings and printed
    # on every label and on the public card
    set_settings("Acme " + PAYLOAD, "Asset " + IMG, "+971 " + ATTR_BREAK)
    for path, what in (("/label/" + AID, "single label"),
                       ("/labels?ids=" + AID, "print sheet"),
                       ("/asset/" + AID, "asset page")):
        h = staff.get(path).get_data(as_text=True)
        clean(h, "hostile branding does not execute on the %s" % what)
    if code:
        h = anon.get("/p/" + code).get_data(as_text=True)
        clean(h, "nor on the public card")

    print()
    print("6. Escaped once, not twice")
    set_settings("Smith & Sons", "Asset No.", "+971 4 000 0000")
    h = staff.get("/label/" + AID).get_data(as_text=True)
    for path, what in (("/label/" + AID, "a label"),
                       ("/labels?ids=" + AID, "a sheet"),
                       ("/asset/" + AID, "the asset page")):
        h = staff.get(path).get_data(as_text=True)
        check("an ampersand prints once on %s" % what, "&amp;amp;" not in h,
              "double-escaping puts &amp;amp; on the printed tag")
        check("and the name is on %s at all" % what,
              "Smith &amp; Sons" in h or "Smith & Sons" in h)

    print()
    print("7. The other label models draw from the same escaped values")
    for model in ("plate", "badge", "strip", "edge"):
        c = A.conn(); cur = c.cursor()
        cur.execute("UPDATE Settings SET label_model=%s, app_name=%s, label_caption=%s WHERE id=1",
                    (model, "Acme " + PAYLOAD, "Cap " + IMG))
        c.commit(); c.close()
        h = staff.get("/label/" + AID).get_data(as_text=True)
        clean(h, "the %s model is safe" % model)

    print()
    print("8. The rule is written down where the renderers can see it")
    src = io.open(os.path.join(ROOT, "app.py"), encoding="utf-8-sig").read()
    check("there is one escape helper", "def _h(" in src and "def _h_row(" in src)
    check("the records are escaped where they are read",
          src.count("_h_row(row_to_dict(") == 2, src.count("_h_row(row_to_dict("))
    check("the shared renderer says its inputs arrive escaped",
          "already HTML-escaped" in src,
          "so nobody adds a second pass and prints &amp;amp;")
finally:
    c = A.conn(); cur = c.cursor()
    cur.execute("UPDATE Settings SET app_name=%s, label_caption=%s, company_phone=%s, label_model='detail' WHERE id=1",
                (BEFORE.get("app_name") or "IT-Vault",
                 BEFORE.get("label_caption") or "Asset No.",
                 BEFORE.get("company_phone") or ""))
    cur.execute("DELETE FROM Assets WHERE _id=%s", [AID])
    c.commit(); c.close()
    print()
    print("(test asset removed, settings put back)")

print()
if fails:
    print("FAILED (%d): %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("ALL PASSED")
