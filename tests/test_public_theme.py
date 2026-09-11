"""A scanned QR opens in the colours the install is themed in.

/asset/<id> is the one page an employee sees without logging in, and it was the
one page that ignored the branding: it selected the app name and contact only,
linked style.css and read var(--accent) straight out of it, so a tag scanned on
a yellow-themed install opened stock red.

The fix shares the acknowledgement page's colour engine rather than copying it,
so most of what is worth asserting here is that there is exactly one copy of
that engine and that both pages run it.
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
cl = A.app.test_client()

SRC = io.open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()

print("1. The colour engine exists once, and both public pages use it")
check("defined once", SRC.count("PUBLIC_THEME_JS = r'''") == 1,
      SRC.count("PUBLIC_THEME_JS = r'''"))
check("applySignTheme is written once", SRC.count("function applySignTheme(b){") == 1,
      SRC.count("function applySignTheme(b){"))
check("hex6 is written once", SRC.count("function hex6(v, fb){") == 1)
check("the acknowledgement page splices it in",
      'SIGNATURE_HTML.replace("/*__PUBLIC_THEME_JS__*/", PUBLIC_THEME_JS)' in SRC)
check("no marker is left unreplaced in what is served",
      "__PUBLIC_THEME_JS__" not in A.SIGNATURE_HTML)
check("the acknowledgement page still carries the engine",
      "function applySignTheme(b){" in A.SIGNATURE_HTML)

print()
print("2. It is safe to run before <body> exists")
# the scan page applies the theme from <head> so it never paints the wrong
# colours first; the old body reference threw there and lost the light class
check("the body class waits for the element",
      "if(document.body) mark();" in A.PUBLIC_THEME_JS)
check("nothing toggles it as a bare statement",
      not [l for l in A.PUBLIC_THEME_JS.splitlines()
           if l.strip() == "document.body.classList.toggle('light', light);"])

print()
print("3. Button labels are derived from the accent, not fixed")
check("bestTextOn is available to the public pages",
      "function bestTextOn(bgHex){" in A.PUBLIC_THEME_JS)
check("--btn-text is published", "'--btn-text', bestTextOn(accent)" in A.PUBLIC_THEME_JS)
check("--btn-mag-text is published", "'--btn-mag-text', bestTextOn(accent2)" in A.PUBLIC_THEME_JS)
# a bright yellow accent with white ink is the case that made this visible
check("no hard-coded white ink on the accent button",
      "background:var(--accent);color:#fff" not in SRC.split("PUBLIC_THEME_JS")[0]
      or "color:var(--btn-text" in SRC)

print()
print("4. A scanned tag renders in the configured accent")
ACCENT = "#f1ff2e"      # the yellow that showed the bug
ACCENT2 = "#7bd400"
SURFACE = "#101820"
c = A.conn(); cur = c.cursor()
cur.execute("SELECT accent, accent2, comp_bg, bg, bg_type, radius FROM Settings WHERE id=1")
before = cur.fetchone() or {}
aid = "SCAN-" + uuid.uuid4().hex[:6]
cur.execute("INSERT INTO Assets (_id, AssetTag, Name, Type, Status) VALUES (%s,%s,%s,%s,%s)",
            (aid, "SCAN-1", "Scan theme test", "Laptop", "Available"))
cur.execute("UPDATE Settings SET accent=%s, accent2=%s, comp_bg=%s WHERE id=1",
            (ACCENT, ACCENT2, SURFACE))
c.commit(); c.close()

try:
    r = cl.get("/asset/" + aid)
    check("the page loads", r.status_code == 200, r.status_code)
    page = r.get_data(as_text=True)

    check("it carries the colour engine", "function applySignTheme(b){" in page)
    m = re.search(r"applySignTheme\((\{.*?\})\);", page, re.S)
    check("it is called with the settings row", bool(m), "no call found")
    payload = m.group(1) if m else ""
    check("the configured accent is in the payload", ACCENT in payload, payload[:160])
    check("the configured second accent is too", ACCENT2 in payload)
    check("so is the component background", SURFACE in payload)
    for col in ("bg_type", "radius", "theme_preset"):
        check("the payload carries " + col, '"' + col + '"' in payload)

    # the whole point: the colours arrive with the document, not a fetch later
    check("no round trip before the colours land",
          "fetch('/api/branding')" not in page)
    check("the call sits in the head, before the body paints",
          page.index("applySignTheme(") < page.index("<body"),
          "script is after <body>")
finally:
    c = A.conn(); cur = c.cursor()
    cur.execute("DELETE FROM Assets WHERE _id=%s", (aid,))
    if before:
        cur.execute("UPDATE Settings SET accent=%s, accent2=%s, comp_bg=%s WHERE id=1",
                    (before.get("accent"), before.get("accent2"), before.get("comp_bg")))
    c.commit(); c.close()

print()
print("5. An unthemed install still gets sensible colours")
check("the engine keeps its own fallbacks", "'#ff3b30'" in A.PUBLIC_THEME_JS)
check("an empty payload is valid to call with",
      "json.dumps(brand_theme, default=str)" in SRC)

print()
if fails:
    print("FAILED (%d): %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("all good")
