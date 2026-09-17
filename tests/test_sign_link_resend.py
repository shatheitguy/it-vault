"""The acknowledgement link can be emailed to the employee it belongs to.

The link went out once, with the assignment mail. If that got buried or the
employee was on leave, the only way to chase it was to copy the link out of the
dialog and paste it into a mail client by hand.

Each send issues a fresh link, which is the part worth testing hardest: the
mailed link has to work, and the one it replaced has to stop working -- and the
link handed back to the dialog has to be the one that was actually mailed, or a
copied link is dead on arrival.

The SMTP conversation is faked; nothing here sends mail.
"""
import os
import re
import smtplib
import sys
import uuid
from urllib.parse import parse_qs, urlparse

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

sent = []


class FakeSMTP:
    def __init__(self, host, port, timeout=None):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, *a, **k):
        pass

    def login(self, *a, **k):
        pass

    def send_message(self, msg):
        sent.append(msg)


def token_of(url):
    return parse_qs(urlparse(url).query).get("token", [""])[0]


def body_text(msg):
    out = []
    for part in msg.walk():
        if part.get_content_maintype() == "text":
            try:
                out.append(part.get_content())
            except Exception:
                pass
    return "\n".join(out)


AID = "RESEND-" + uuid.uuid4().hex[:6]
EMP = "EMP-RESEND-" + uuid.uuid4().hex[:4]
EMAIL = "resend.test@example.com"

c = A.conn(); cur = c.cursor()
cur.execute("SELECT smtp_host, smtp_port, smtp_user, smtp_pass, smtp_from FROM Settings WHERE id=1")
smtp_before = cur.fetchone() or {}
cur.execute("INSERT INTO Assets (_id, AssetTag, Name, Type, Status, Serial) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (AID, "RS-1", "Resend test laptop", "Laptop", "Assigned", "SN-RS-1"))
# no SMTP, nobody assigned yet
cur.execute("UPDATE Settings SET smtp_host='', smtp_user='', smtp_pass='', smtp_from='' WHERE id=1")
c.commit(); c.close()

real_smtp = smtplib.SMTP
smtplib.SMTP = FakeSMTP
try:
    print("1. The dialog is told who the link can go to")
    r = cl.get("/api/assets/" + AID + "/sign/link")
    check("a link is issued", r.status_code == 200, r.status_code)
    j = r.get_json()
    check("nobody is named yet", j.get("assignee") == "", repr(j.get("assignee")))
    check("so emailing is not offered", j.get("can_email") is False, j.get("can_email"))
    check("and it says mail is not set up", j.get("smtp_ready") is False)
    first_url = j.get("url") or ""
    check("the link is a /sign URL", "/sign?token=" in first_url, first_url[:60])

    print()
    print("2. Sending is refused for a reason, not silently")
    r = cl.post("/api/assets/" + AID + "/sign/send")
    check("unassigned asset is refused", r.status_code == 400, r.status_code)
    check("and says to assign it first", "not assigned" in (r.get_json().get("error") or ""),
          r.get_json().get("error"))
    check("nothing was sent", not sent, len(sent))

    c = A.conn(); cur = c.cursor()
    cur.execute("INSERT INTO Employees (_id, EmployeeID, EmployeeName, Email) "
                "VALUES (%s,%s,%s,%s)", (uuid.uuid4().hex, EMP, "Resend Tester", ""))
    cur.execute("UPDATE Assets SET EmployeeID=%s WHERE _id=%s", (EMP, AID))
    c.commit(); c.close()

    r = cl.post("/api/assets/" + AID + "/sign/send")
    check("an employee with no email is refused", r.status_code == 400, r.status_code)
    err = r.get_json().get("error") or ""
    check("and is named in the message", "Resend Tester" in err, err)
    check("still nothing sent", not sent, len(sent))

    c = A.conn(); cur = c.cursor()
    cur.execute("UPDATE Employees SET Email=%s WHERE EmployeeID=%s", (EMAIL, EMP))
    c.commit(); c.close()

    r = cl.post("/api/assets/" + AID + "/sign/send")
    check("no SMTP configured is refused", r.status_code == 400, r.status_code)
    check("and points at Settings", "SMTP" in (r.get_json().get("error") or ""),
          r.get_json().get("error"))
    check("and sent nothing", not sent, len(sent))

    print()
    print("3. With an address and a mail server, it goes")
    c = A.conn(); cur = c.cursor()
    cur.execute("UPDATE Settings SET smtp_host=%s, smtp_port=%s, smtp_from=%s WHERE id=1",
                ("smtp.invalid", 587, "vault@example.com"))
    c.commit(); c.close()

    r = cl.get("/api/assets/" + AID + "/sign/link")
    j = r.get_json()
    check("the dialog now offers it", j.get("can_email") is True, j)
    check("naming the employee", j.get("assignee") == "Resend Tester", j.get("assignee"))
    check("and the address", j.get("assignee_email") == EMAIL, j.get("assignee_email"))
    stale_url = j.get("url") or ""

    r = cl.post("/api/assets/" + AID + "/sign/send")
    check("the send succeeds", r.status_code == 200, r.status_code)
    j2 = r.get_json()
    check("it reports the address", j2.get("sent_to") == EMAIL, j2.get("sent_to"))
    check("exactly one mail went out", len(sent) == 1, len(sent))

    msg = sent[0] if sent else None
    if msg:
        check("addressed to the employee", str(msg["To"]) == EMAIL, str(msg["To"]))
        # a mail that reads like a first notification is confusing when it is
        # the second or third
        check("the subject reads as a reminder",
              "Reminder" in str(msg["Subject"]), str(msg["Subject"]))
        check("the asset is identified", "Resend test laptop" in str(msg["Subject"]),
              str(msg["Subject"]))
        text = body_text(msg)
        check("the body carries a sign link", "/sign?token=" in text)
        check("it is the link handed back to the dialog",
              (j2.get("url") or "x") in text, j2.get("url"))

    print()
    print("4. The mailed link works and the one before it does not")
    mailed = token_of(j2.get("url") or "")
    check("the mailed link is accepted",
          cl.get("/api/assets/sign/verify?token=" + mailed).status_code == 200,
          cl.get("/api/assets/sign/verify?token=" + mailed).status_code)
    r = cl.get("/api/assets/sign/verify?token=" + token_of(stale_url))
    check("the link it replaced is refused", r.status_code == 400, r.status_code)
    check("saying a newer one was issued",
          "newer one" in (r.get_json().get("error") or ""), r.get_json().get("error"))

    print()
    print("5. Sending again replaces it again")
    sent.clear()
    r = cl.post("/api/assets/" + AID + "/sign/send")
    check("the second send succeeds", r.status_code == 200, r.status_code)
    second = r.get_json().get("url") or ""
    check("it is a different link", second != j2.get("url"))
    check("the new one works",
          cl.get("/api/assets/sign/verify?token=" + token_of(second)).status_code == 200)
    check("the first mailed link is now dead",
          cl.get("/api/assets/sign/verify?token=" + mailed).status_code == 400)

    print()
    print("6. It is on the record")
    c = A.conn(); cur = c.cursor()
    cur.execute("SELECT action, detail FROM AuditLog WHERE asset_id=%s "
                "AND action='SIGN_LINK_SENT' ORDER BY id DESC", [AID])
    rows = cur.fetchall(); c.close()
    check("both sends were logged", len(rows) == 2, len(rows))
    check("with the address they went to",
          bool(rows) and EMAIL in (rows[0].get("detail") or ""),
          rows[0].get("detail") if rows else "no rows")

    print()
    print("7. The assignment mail issues the same kind of link")
    # it used to mint a token with no nonce, so issuing a new link retired
    # nothing -- the old email stayed valid
    src = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
    i = src.index("def notify_person_asset_assigned(")
    fn = src[i:src.index("\ndef ", i + 10)]
    check("it goes through the shared issuer", "_issue_sign_link(" in fn)
    check("it does not mint a bare token", "_sign_token({" not in fn, fn.count("_sign_token({"))

    print()
    print("8. The dialog actually offers it")
    idx = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    js = open(os.path.join(ROOT, "app.js"), encoding="utf-8").read()
    css = open(os.path.join(ROOT, "style.css"), encoding="utf-8").read()
    check("the modal has the send row", 'id="signMailRow"' in idx)
    check("it names who it goes to", 'id="signMailWho"' in idx)
    check("and has the button", 'id="signMailBtn"' in idx)
    check("the button is wired", "signMailBtn').onclick=emailSignLink" in js)
    check("the dialog is told the target", "showSignMailTarget(" in js)
    check("a send refreshes the shown link", "if(j.url)document.getElementById('signUrl')" in js)
    # a bright accent button that does nothing is worse than no button: there
    # was no .btn:disabled rule at all, so every switched-off button in the app
    # looked live
    check("a disabled button reads as disabled",
          ".btn:disabled,.btn[disabled]{" in css)
    check("and does not brighten on hover", ".btn:disabled:hover" in css)
    # The browser caches these aggressively; a UI change nobody sees is no
    # change. Asserting the intent -- both assets carry the same token, so
    # they are bumped together -- rather than pinning today's literal value,
    # which made this fail on the next bump for no good reason.
    m_js = re.search(r"app\.js\?nocache=([A-Za-z0-9]+)", idx)
    m_css = re.search(r"style\.css\?v=([A-Za-z0-9]+)", idx)
    check("app.js is cache-busted", bool(m_js), m_js.group(1) if m_js else "none")
    check("style.css is cache-busted", bool(m_css), m_css.group(1) if m_css else "none")
    check("both carry the same token, so a change ships as one",
          bool(m_js) and bool(m_css) and m_js.group(1) == m_css.group(1),
          "%s vs %s" % (m_js.group(1) if m_js else "?", m_css.group(1) if m_css else "?"))
finally:
    smtplib.SMTP = real_smtp
    c = A.conn(); cur = c.cursor()
    cur.execute("DELETE FROM Assets WHERE _id=%s", (AID,))
    cur.execute("DELETE FROM Employees WHERE EmployeeID=%s", (EMP,))
    cur.execute("DELETE FROM AuditLog WHERE asset_id=%s", (AID,))
    cur.execute("UPDATE Settings SET smtp_host=%s, smtp_port=%s, smtp_user=%s, "
                "smtp_pass=%s, smtp_from=%s WHERE id=1",
                (smtp_before.get("smtp_host"), smtp_before.get("smtp_port"),
                 smtp_before.get("smtp_user"), smtp_before.get("smtp_pass"),
                 smtp_before.get("smtp_from")))
    c.commit(); c.close()
    print()
    print("(test asset and employee removed, SMTP settings restored)")

print()
if fails:
    print("FAILED (%d): %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("ALL PASSED")
