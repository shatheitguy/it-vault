"""A dashboard tile can wear the icon of the thing it points at.

The browser cannot fetch that icon itself: the target is another origin, and
usually plain http on the LAN, so CORS and mixed-content rules both block it.
The server can, and hands back a small data URI the layout stores inline --
no second request when the dashboard loads, and no broken image when the
target is only reachable from the server.

That last property is the point and also the risk: this will fetch a private
address, because the tiles people want are the UniFi controller, the NAS, the
switch. So it is gated on settings:write -- the same permission as changing
branding -- and it returns only a re-encoded PNG, never the response body.
"""
import io
import os
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


def read(*parts):
    return io.open(os.path.join(ROOT, *parts), encoding="utf-8-sig").read()


A.app.config["TESTING"] = True
admin = A.app.test_client()
with admin.session_transaction() as s:
    s["user"] = "admin"
    s["role"] = "admin"


def icon(url, cl=admin):
    r = cl.get("/api/widget/icon", query_string={"url": url})
    return r.status_code, (r.get_json() or {})


print("1. It refuses what it should, with a reason")
code, j = icon("")
check("no address is rejected", code == 400, j.get("error"))
for bad in ("ftp://x", "file:///etc/passwd", "javascript:alert(1)", "gopher://x"):
    code, j = icon(bad)
    check("%-24s is rejected" % bad, code == 400, "%s %s" % (code, j.get("error")))
check("and says which schemes are allowed",
      "http" in (icon("ftp://x")[1].get("error") or ""))

print()
print("2. It requires permission, not just a session")
anon = A.app.test_client()
code, _ = icon("http://localhost:5000/", anon)
check("signed out is refused", code == 401, code)
# read-only must not be able to aim the server at arbitrary addresses
reader = A.app.test_client()
with reader.session_transaction() as s:
    s["user"] = "viewer"
    s["role"] = "read-only"
code, _ = icon("http://localhost:5000/", reader)
check("read-only is refused", code == 403, code)

print()
print("3. It finds an icon the page declares")
# the app declares its own logo, which is exactly the shape of a real lookup:
# fetch the page, parse <link rel=icon>, fetch and re-encode that
head = read("index.html")[:1200]
check("the app declares one to find", 'rel="icon"' in head)

print()
print("4. A direct image address is used as-is")
# someone pasting a PNG should not be told there is no icon at it
check("the route handles an image content-type",
      'low.startswith("image/")' in read("app.py"))
check("and does not depend on /favicon.ico existing",
      'candidates.append(origin + "/favicon.ico")' in read("app.py"))

print()
print("5. What comes back is a re-encoded PNG, never the fetched bytes")
src = read("app.py")
i = src.index("def widget_icon()")
fn = src[i:src.index("\n@app.route", i)]
check("it re-encodes through _fit_png", "_fit_png(data, 64," in fn)
check("it is capped in size", "MAX_BYTES" in fn and "512 * 1024" in fn)
check("it is capped in time", "timeout=6" in fn)
check("it returns a data URI", '"data:image/png;base64,"' in fn)
check("it never returns the raw body", "return data" not in fn and "r.read()" not in fn)
check("it tries only a handful of candidates", "candidates[:6]" in fn)

print()
print("6. The layout keeps the tiles, and a wipe does not eat them")
appjs = read("app.js")
check("layout v2 exists", "itvault_dash_layout_v2" in appjs)
check("v1 is migrated rather than dropped",
      "if(Array.isArray(v1)) L.order=v1;" in appjs)
check("a local wipe preserves the layout",
      "'itvault_dash_layout_v2'" in appjs.split("const KEEP=new Set([")[1][:200])
check("tiles open safely whichever target is chosen",
      'rel="noopener noreferrer"' in appjs)
check("only http(s) tiles can be added", "/^https?:" in appjs)
check("columns are bounded 1-4", "Math.max(1, Math.min(4," in appjs)

print()
print("7. Tiles read the heartbeat fetch the dashboard already makes")
check("no second poller", appjs.count("paintLinkStates(") >= 2)
check("bound to a monitor id", 'data-mon="${t.monitor' in appjs)

print()
print("8. The dashboard-shaped extras")
idx = read("index.html")
css = read("style.css")
check("there is a filter box", 'id="dashFilter"' in idx)
check("a non-matching widget is hidden, not dimmed",
      "#dashWidgets .widget.w-nomatch{display:none}" in css)
check("the filter searches the address too",
      ".wlink-body')?.getAttribute('href')" in appjs)
check("a tile can carry a subtitle", 'id="wmDesc"' in idx and "wlink-sub" in appjs)
check("a tile can open in this tab", 'id="wmTarget"' in idx)
# _self is offered, but a page opened from here must never get a handle on
# this one, so noopener is not negotiable
check("noopener survives either target",
      appjs.count('rel="noopener noreferrer"') >= 1
      and "const tgt=(t.target==='_self')?'_self':'_blank';" in appjs)

print()
print("9. The layout is stored per user, so it is in the backup")
# It lived in localStorage, which meant one browser's opinion: gone on a new
# machine, gone with a cleared cache, and absent from every backup.
LAYOUT = {"v": 2, "cols": 3, "order": ["tickets", "link:a"], "hidden": ["feed"],
          "links": [{"key": "link:a", "title": "NAS", "url": "http://10.0.0.9:5000"}]}
r = admin.get("/api/dash/layout")
check("it can be read", r.status_code == 200, r.status_code)
r = admin.put("/api/dash/layout", json={"layout": LAYOUT})
check("it can be saved", r.status_code == 200, r.get_json())
got = (admin.get("/api/dash/layout").get_json() or {}).get("layout")
check("it round-trips byte for byte", got == LAYOUT, got)

for body, why in ((None, "no body"), ({"layout": []}, "a list"),
                  ({"layout": "nope"}, "a string")):
    r = admin.put("/api/dash/layout", json=body)
    check("%-10s is rejected" % why, r.status_code == 400,
          "%s %s" % (r.status_code, (r.get_json() or {}).get("error")))
# icons are inline data URIs, so a layout is bigger than it looks
r = admin.put("/api/dash/layout", json={"layout": {"v": 2, "b": "x" * (600 * 1024)}})
check("an oversized layout is refused", r.status_code == 413, r.status_code)
check("signed out is refused",
      A.app.test_client().get("/api/dash/layout").status_code == 401)

# the reason it moved to the server at all
import zipfile
fname = A._run_backup("all")
path = os.path.join(A.BACKUP_DIR, fname)
text = ""
if zipfile.is_zipfile(path):
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            if n.endswith(".sql"):
                text = z.read(n).decode("utf-8", "replace")
else:
    text = io.open(path, encoding="utf-8").read()
check("a backup carries the dash_layout column", "dash_layout" in text)
check("and the tiles inside it", "10.0.0.9" in text)

print()
print("10. The browser copy is a cache, not the record")
check("saving writes through to the server", "'/api/dash/layout', {method:'PUT'" in appjs)
check("and still paints from the local copy first",
      "localStorage.setItem(DASH_LAYOUT_KEY2" in appjs)
check("a visit re-reads the stored layout", "syncDashLayout()" in appjs)
check("a failed save says what did not happen",
      "Saved on this device only" in appjs)
check("export/import is gone", "dashExport" not in appjs and "dashExport" not in idx)

print()
if fails:
    print("FAILED (%d): %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("ALL PASSED")
