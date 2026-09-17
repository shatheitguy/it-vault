"""Every email IT-Vault sends signs off the same way.

The footer carries three things, in this order: the organisation's own name,
because to whoever opens the mail it is from them; then, smaller, what sent
it and which version; then where to find the project and the person who wrote
it.

Two reasons this is a test rather than a convention. Mail is sent from nine
different places in app.py -- OTP codes, password resets, ticket updates,
heartbeat alerts, signed handovers, the SMTP check -- and a new one is easy to
add without the footer. And the version in it goes stale silently, because
nobody reads their own footer.
"""

import io
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
import app as A

fails = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (("   " + str(detail)) if detail else ""))
    if not cond:
        fails.append(name)


BRAND = "Northside Sports Club"
text = A._email_footer(BRAND)
html = A._email_footer_html(BRAND)
src = io.open(os.path.join(ROOT, "app.py"), encoding="utf-8-sig").read()

print("\nthe plain-text footer")
check("starts on its own, after a rule", text.startswith("\n\n—\n"),
      "it has to be separable from the message above it")
lines = [l for l in text.strip().splitlines() if l.strip() and l.strip() != "—"]
check("is two lines", len(lines) == 2, lines)
check("the organisation comes first", lines[0] == BRAND, lines[0])
check("the credit line comes second", lines[1].startswith("IT-Vault v"), lines[1])
check("it names the running version", A.APP_VERSION in text, A.APP_VERSION)
check("it spells out both URLs, since text cannot link",
      "https://github.com/shatheitguy/it-vault" in text and "https://shatheitguy.in" in text)

print("\nthe HTML footer")
check("the organisation is larger than the credit",
      "font-size:12px" in html and "font-size:10px" in html,
      "12px over 10px")
check("the organisation is the 12px line",
      re.search(r"font-size:12px[^>]*>" + re.escape(BRAND), html) is not None)
check("the credit is the 10px line",
      re.search(r"font-size:10px.*?IT-Vault v", html, re.S) is not None)
check("Sha The IT Guy is a link to shatheitguy.in",
      re.search(r'<a href="https://shatheitguy\.in"[^>]*>Sha The IT Guy</a>', html) is not None,
      "this is the one the request was actually about")
check("the project is a link too",
      '<a href="https://github.com/shatheitguy/it-vault"' in html)
check("every style is inline", "<style" not in html and "class=" not in html,
      "mail clients strip style blocks")
check("the separator is an entity, not a raw character",
      "&middot;" in html and "·" not in html,
      "a client that ignores the MIME charset renders the raw one as mojibake")
check("a brand name with markup in it cannot break the footer",
      "&lt;b&gt;" in A._email_footer_html("<b>x</b>"),
      "an organisation called <b>Something</b> would otherwise inject markup")

print("\nit reaches every message")
missing = []
for m in re.finditer(r"set_content\(", src):
    window = src[m.start():m.start() + 400]
    if "_email_footer(" not in window:
        line = src[:m.start()].count("\n") + 1
        missing.append(line)
check("every plain-text body appends it", not missing,
      "app.py lines without it: %s" % missing)
check("there are as many send sites as we think", src.count("set_content(") >= 8,
      "%d found" % src.count("set_content("))

print("\nand the HTML alternative gets the HTML one")
window = src[src.index("if html_body:"):][:700]
check("the HTML part is given the HTML footer", "_email_footer_html(bn)" in window)
check("it goes inside <body>", '"</body>"' in window,
      "some clients drop what comes after </body>, and Gmail clips it")
check("the button template declares a charset",
      '<meta charset="utf-8">' in src.split("def _button_email_html")[1][:600])

print("\nthe version cannot go stale")
check("the footer reads APP_VERSION rather than a literal",
      "IT-Vault v{APP_VERSION}" in src,
      "a hand-typed version is one nobody remembers to change")

print()
if fails:
    print("FAILED (%d): %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("ALL PASSED")
