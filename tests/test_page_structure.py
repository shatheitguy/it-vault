"""The shipped HTML is well formed.

This exists because it was not, and the damage reached a real server. Moving
the notification channel manager out of a modal and into Settings dragged the
modal's footer along with it -- a stray CLOSE button and two extra `</div>`.
Two unbalanced tags closed the settings container early, so every section
after Notifications (SLA, Database, LDAP, UniFi, Branding, Custom Asset,
Danger) fell outside its wrapper and the page rendered as a mess. A dangling
`getElementById('hbChanClose').onclick` then threw at load, which stops every
script after it and leaves Heartbeat blank.

Nothing failed at build or on push. The browser does not complain about extra
closing tags, it just silently reparents everything, so the first report came
from someone using it. These checks are cheap and would have caught both.
"""
import io
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

fails = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (("   " + str(detail)) if detail else ""))
    if not cond:
        fails.append(name)


def read(name):
    return io.open(os.path.join(ROOT, name), encoding="utf-8-sig").read()


PAGES = ["index.html", "login.html", "portal.html", "monitor.html"]

print("1. Tags balance")
for page in PAGES:
    if not os.path.exists(os.path.join(ROOT, page)):
        continue
    html = read(page)
    for tag in ("div", "section"):
        opens = len(re.findall(r"<%s\b" % tag, html))
        closes = len(re.findall(r"</%s>" % tag, html))
        check("%-13s <%s> balances" % (page, tag), opens == closes,
              "%d open, %d close (%+d)" % (opens, closes, opens - closes))

print()
print("2. Every settings section is a sibling, not nested in another")
html = read("index.html")
# depth-walk the settings wrapper: a section that opens before the previous
# one closes is the exact shape of the bug
start = html.index('<div class="cfgwrap"')
depth, i, end = 0, start, -1
while i < len(html):
    if html.startswith("<div", i):
        depth += 1
    elif html.startswith("</div>", i):
        depth -= 1
        if depth == 0:
            end = i + 6
            break
    i += 1
check("the settings wrapper closes", end > 0)
wrap = html[start:end]
SEC_RE = r'<section[^>]*class="[^"]*cfg-sec[^"]*"[^>]*data-sec="([a-z]+)"'
secs = re.findall(SEC_RE, wrap)
check("all the sections are inside it", len(secs) >= 10, secs)
check("it opens and closes the same number of sections",
      len(re.findall(r"<section\b", wrap)) == len(re.findall(r"</section>", wrap)))

for sec in secs:
    m = re.search(SEC_RE.replace("([a-z]+)", sec), wrap)
    body = wrap[m.start():wrap.index("</section>", m.start())]
    o = len(re.findall(r"<div\b", body))
    c = len(re.findall(r"</div>", body))
    check("  %-9s section balances" % sec, o == c, "%+d" % (o - c))

print()
print("3. Every nav item has a section, and every section has a nav item")
# "cfgitem active", "cfgitem cfgitem-danger" -- the marker is one class
# among several, not the whole attribute
nav = re.findall(r'<button[^>]*class="[^"]*cfgitem[^"]*"[^>]*data-sec="([a-z]+)"', html)
check("nav items found", len(nav) >= 10, nav)
check("no nav item points at a missing section", not (set(nav) - set(secs)),
      sorted(set(nav) - set(secs)))
check("no section is unreachable from the nav", not (set(secs) - set(nav)),
      sorted(set(secs) - set(nav)))

print()
print("4. No script binds to an element that does not exist")
# An unguarded getElementById(...).onclick on a missing element throws, and a
# throw at the top level of app.js stops everything after it -- which is what
# turned a markup slip into a blank Heartbeat page.
js = read("app.js")
ids = set(re.findall(r'id="([A-Za-z0-9_\-]+)"', html))
# only top-level binds matter: one inside a function runs when called, by
# which time the element may have been created
lines = js.split("\n")
dangling = []
for n, line in enumerate(lines, 1):
    if line.startswith((" ", "\t")):
        continue                      # indented -- inside a function or block
    m = re.match(r"document\.getElementById\('([A-Za-z0-9_\-]+)'\)\.(on\w+)\s*=", line)
    if m and m.group(1) not in ids:
        dangling.append("%s:%d %s" % ("app.js", n, m.group(1)))
check("nothing at the top level binds to a missing element",
      not dangling, dangling[:4])

print()
print("5. Nothing refers to the parts that were removed")
for gone in ("hbChanModal", "hbChanBtn", "hbChanClose"):
    check("  %-12s is gone from both files" % gone,
          gone not in html and gone not in js,
          "html=%s js=%s" % (gone in html, gone in js))
# and the channel form really did land in the notifications section
notif_at = re.search(SEC_RE.replace("([a-z]+)", "notif"), html).start()
notif_end = html.index("</section>", notif_at)
check("the channel form is inside Settings > Notifications",
      notif_at < html.index('id="hbc_kind"') < notif_end)

print()
if fails:
    print("FAILED (%d): %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("ALL PASSED")
