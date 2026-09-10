"""Notifications arrive from the organisation, not from a mailbox.

Every sender set From to a bare address, so an inbox showed it@example.com in
the sender column. Recipients include people who have never logged in and know
the install only by the name it is branded as.

The SMTP conversation is faked -- nothing here sends mail -- so the assertions
are about the header that would go out.
"""
import io
import os
import smtplib
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


SRC = io.open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()

print("1. The header is built from the branding name")
check("a bare address gets the brand in front of it",
      A._mail_from("it@example.com", "Riverside Sports") == "Riverside Sports <it@example.com>",
      A._mail_from("it@example.com", "Riverside Sports"))
check("no brand configured falls back to the product name",
      A._mail_from("it@example.com", "") == "IT-Vault <it@example.com>",
      A._mail_from("it@example.com", ""))
check("a name the admin set themselves is left alone",
      A._mail_from("IT Helpdesk <it@example.com>", "Riverside Sports")
      == "IT Helpdesk <it@example.com>",
      A._mail_from("IT Helpdesk <it@example.com>", "Riverside Sports"))
# a brand with a comma or a quote in it would split the header into two
# addresses if it were pasted in raw
check("a name that would break the header is quoted",
      A._mail_from("it@example.com", "Riverside, Inc") == '"Riverside, Inc" <it@example.com>',
      A._mail_from("it@example.com", "Riverside, Inc"))
check("a non-ASCII name is encoded, not dropped",
      "@example.com" in A._mail_from("it@example.com", "مؤسسة المثال")
      and "=?utf-8?" in A._mail_from("it@example.com", "مؤسسة المثال").lower(),
      A._mail_from("it@example.com", "مؤسسة المثال"))
# nothing parseable to decorate: hand back what was configured rather than
# inventing a header that would bounce
check("an unusable From is passed through untouched",
      A._mail_from("not-an-address", "Riverside Sports") == "not-an-address",
      A._mail_from("not-an-address", "Riverside Sports"))
check("an empty From stays empty", A._mail_from("", "Riverside Sports") == "")
check("None does not raise", A._mail_from(None, "Riverside Sports") == "")

print()
print("2. No sender writes a bare address any more")
bare = [ln.strip() for ln in SRC.splitlines()
        if 'msg["From"]' in ln and "_mail_from(" not in ln]
check("every From goes through the helper", not bare, bare[:3])
check("all nine senders are covered", SRC.count('msg["From"] = _mail_from(') == 9,
      SRC.count('msg["From"] = _mail_from('))

print()
print("3. A real notification carries it")
BRAND = "Mail Header Test"
FROM_ADDR = "vault-test@example.com"
sent = []


class FakeSMTP:
    def __init__(self, host, port, timeout=None):
        sent.append(("connect", host, port))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, *a, **k):
        pass

    def login(self, *a, **k):
        pass

    def send_message(self, msg):
        sent.append(("msg", msg))


c = A.conn(); cur = c.cursor()
cur.execute("SELECT app_name, smtp_host, smtp_port, smtp_user, smtp_pass, smtp_from "
            "FROM Settings WHERE id=1")
before = cur.fetchone() or {}
cur.execute("UPDATE Settings SET app_name=%s, smtp_host=%s, smtp_port=%s, smtp_user=%s, "
            "smtp_pass=%s, smtp_from=%s WHERE id=1",
            (BRAND, "smtp.invalid", 587, "", "", FROM_ADDR))
c.commit(); c.close()

real_smtp = smtplib.SMTP
smtplib.SMTP = FakeSMTP
try:
    ok = A._send_simple_email("someone@example.com", "Test subject", "body text")
    check("the send reported success", ok is True, ok)
    msgs = [rest[0] for kind, *rest in sent if kind == "msg"]
    check("one message was handed to SMTP", len(msgs) == 1, len(msgs))
    if msgs:
        hdr = str(msgs[0]["From"])
        check("the sender line leads with the branding name",
              hdr == BRAND + " <" + FROM_ADDR + ">", hdr)
        check("the address is still there for the mail server", FROM_ADDR in hdr, hdr)
        # send_message takes the envelope sender from this header, so it has to
        # stay parseable -- a broken one would make every notification bounce
        from email.utils import parseaddr
        check("it parses back to exactly that address",
              parseaddr(hdr)[1] == FROM_ADDR, parseaddr(hdr))
        check("and back to the branding name", parseaddr(hdr)[0] == BRAND, parseaddr(hdr))

    # with no From address configured, the SMTP username is used -- and still
    # gets the name
    sent.clear()
    c = A.conn(); cur = c.cursor()
    cur.execute("UPDATE Settings SET smtp_from='', smtp_user=%s WHERE id=1",
                ("login@example.com",))
    c.commit(); c.close()
    A._send_simple_email("someone@example.com", "Test subject", "body text")
    msgs = [rest[0] for kind, *rest in sent if kind == "msg"]
    check("the fallback address is named too",
          bool(msgs) and str(msgs[0]["From"]) == BRAND + " <login@example.com>",
          str(msgs[0]["From"]) if msgs else "no message")
finally:
    smtplib.SMTP = real_smtp
    c = A.conn(); cur = c.cursor()
    cur.execute("UPDATE Settings SET app_name=%s, smtp_host=%s, smtp_port=%s, smtp_user=%s, "
                "smtp_pass=%s, smtp_from=%s WHERE id=1",
                (before.get("app_name"), before.get("smtp_host"), before.get("smtp_port"),
                 before.get("smtp_user"), before.get("smtp_pass"), before.get("smtp_from")))
    c.commit(); c.close()
    print()
    print("(SMTP settings restored)")

print()
if fails:
    print("FAILED (%d): %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("all good")
