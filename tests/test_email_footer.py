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
check("it carries no URLs at all",
      "http" not in text,
      "mail security rewrites every link it can see; in a text part the reader "
      "sees the rewrite -- 200 characters of clicktime proxy, twice, every message")
check("but it still names the author", "Sha The IT Guy" in text)

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
check("the links live only in the HTML part, where a rewrite is invisible",
      "http" in html and "http" not in text,
      "the reader sees the anchor text, whatever the gateway does to the href")
check("every style is inline", "<style" not in html and "class=" not in html,
      "mail clients strip style blocks")
check("the separator is an entity, not a raw character",
      "&middot;" in html and "·" not in html,
      "a client that ignores the MIME charset renders the raw one as mojibake")
check("a brand name with markup in it cannot break the footer",
      "&lt;b&gt;" in A._email_footer_html("<b>x</b>"),
      "an organisation called <b>Something</b> would otherwise inject markup")

print("\nit reaches every message")
# Six senders build their own EmailMessage in this file, and each one used to
# set its own body. The ones that remembered got the plain-text footer; only
# the acknowledgement mail ever had an HTML part, so only that one had links
# -- which is why the signed-PDF mail arrived with the branding and the
# credit as dead text. There is one signer now, and everything goes through
# it.
sites = src.count("_with_email_footer(")
check("every sender goes through one signer", sites >= 9, "%d call sites" % sites)
check("and only the signer sets a body", src.count("set_content(") == 1,
      "%d bodies built by hand" % src.count("set_content("))
check("the text footer is appended in exactly one place",
      src.count("+ _email_footer(bn)") == 1,
      "five senders appending it by hand is what left them with no HTML part")

print("\nan attachment does not cost you the footer")
from email.message import EmailMessage
_m = EmailMessage()
_m["Subject"] = "Signed asset acknowledgement"
_m["From"] = "it@example.com"
_m["To"] = "someone@example.com"
A._with_email_footer(_m, BRAND, "The signed copy is attached as a PDF.")
_m.add_attachment(b"%PDF-1.4", maintype="application", subtype="pdf",
                  filename="IT-0042_signed.pdf")
_parts = [p.get_content_type() for p in _m.walk()]
check("the message is still multipart/mixed", _m.get_content_type() == "multipart/mixed")
check("with both body parts inside it",
      "text/plain" in _parts and "text/html" in _parts, _parts)
check("and the PDF beside them", "application/pdf" in _parts, _parts)
_html = [p.get_content() for p in _m.walk() if p.get_content_type() == "text/html"][0]
check("the organisation is named", BRAND in _html)
check("the project is a live link", '<a href="https://github.com/shatheitguy/it-vault"' in _html,
      "this is the one the request was about: no hyperlink on the signed PDF mail")
check("so is the author", '<a href="https://shatheitguy.in"' in _html)
_text = [p.get_content() for p in _m.walk() if p.get_content_type() == "text/plain"][0]
check("the text part still carries no URLs", "http" not in _text)
check("a body with markup in it cannot inject any",
      "&lt;b&gt;" in A._email_html_from_text("<b>x</b>"))
check("line breaks survive into the HTML part",
      "<br>" in A._email_html_from_text("one\ntwo"))

print("\nand it is not an email-only idea")
# A Telegram alert used to arrive as two bare lines with nothing saying which
# system sent it. The medium does not get to decide that.
_tg = A._chat_footer("html")
check("Telegram gets real links",
      '<a href="https://github.com/shatheitguy/it-vault">' in _tg
      and '<a href="https://shatheitguy.in">' in _tg, _tg)
check("the version is in it", A.APP_VERSION in _tg)
check("the separator is an entity, not a raw character",
      "&#183;" in _tg and "·" not in _tg,
      "Telegram parses the text as HTML")
tg_src = src[src.index("def _hb_send_telegram("):]
tg_src = tg_src[:tg_src.index("\n\n_HB_SENDERS")]
check("it is sent in HTML mode", '"parse_mode": "HTML"' in tg_src)
check("and what came from the event is escaped first",
      "_e(subject)" in tg_src and "_e(body)" in tg_src,
      'an asset called "<Laptop>" would otherwise be refused by Telegram')

_sl = A._chat_footer("mrkdwn")
check("Slack gets links in its own markup",
      "<https://github.com/shatheitguy/it-vault|IT-Vault v" in _sl
      and "|Sha The IT Guy>" in _sl, _sl)
check("a channel with no markup still gets the names",
      "Sha The IT Guy" in A._chat_footer("text")
      and "<" not in A._chat_footer("text"))
check("every chat footer names the install",
      all(A._brand_name() in A._chat_footer(m) for m in ("html", "mrkdwn", "text")))

wh = src[src.index('payload = {"event": "notification"'):][:700]
check("a webhook is told the same provenance, as fields",
      '"version": APP_VERSION' in wh and '"author_url": AUTHOR_URL' in wh,
      "whoever is on the other end should not have to parse it out of a string")

print("\nthe version cannot go stale")
check("the footer reads APP_VERSION rather than a literal",
      "IT-Vault v{APP_VERSION}" in src,
      "a hand-typed version is one nobody remembers to change")

print()
if fails:
    print("FAILED (%d): %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("ALL PASSED")
