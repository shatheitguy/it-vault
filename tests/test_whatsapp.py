"""The acknowledgement link and the signed copy go out on WhatsApp too.

The WhatsApp link itself (whatsapp/bridge.mjs, Baileys) can't be exercised
here -- it needs a phone to scan a QR -- so wa.is_on / wa.send are faked and
what is checked is everything around them: who gets what, what the dialog
and the sign page are told, that signing no longer waits for the mail
server, and that the success message is something a person will see.
"""
import os
import sys
import time
import uuid

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
import app as A
import wa

A.init_db()
A.migrate_schema()

fails = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (("   " + str(detail)) if detail else ""))
    if not cond:
        fails.append(name)


print("1. Phone numbers come out the way WhatsApp wants them")
for raw, cc, want in [("050 123 4567", "971", "971501234567"),
                      ("501234567", "971", "971501234567"),
                      ("+971 50 123 4567", "971", "971501234567"),
                      ("00971501234567", "971", "971501234567"),
                      ("971501234567", "971", "971501234567"),
                      ("+91 98765 43210", "971", "919876543210"),
                      ("98765 43210", "91", "919876543210"),
                      ("123", "971", ""), ("", "971", ""), ("abc", "971", "")]:
    got = wa.normalize(raw, cc)
    check(f"{raw!r} ({cc}) -> {want!r}", got == want, got)

A.app.config["TESTING"] = True
cl = A.app.test_client()
with cl.session_transaction() as sess:
    sess["user"] = "admin"
    sess["role"] = "admin"

AID = "WA-" + uuid.uuid4().hex[:6]
EMP = "EMP-WA-" + uuid.uuid4().hex[:4]
EID = uuid.uuid4().hex

c = A.conn(); cur = c.cursor()
cur.execute("SELECT smtp_host, smtp_port, smtp_user, smtp_pass, smtp_from, "
            "wa_country_code, wa_send_link, wa_send_pdf FROM Settings WHERE id=1")
before = cur.fetchone() or {}
cur.execute("INSERT INTO Assets (_id, AssetTag, Name, Type, Status, Serial, EmployeeID) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (AID, "WA-1", "WhatsApp test laptop", "Laptop", "Assigned", "SN-WA-1", EMP))
cur.execute("INSERT INTO Employees (_id, EmployeeID, EmployeeName, Email) VALUES (%s,%s,%s,%s)",
            (EID, EMP, "Wa Tester", ""))
cur.execute("UPDATE Settings SET smtp_host='', wa_country_code='971', wa_send_link=1, wa_send_pdf=1 WHERE id=1")
c.commit(); c.close()

sent = []
real_is_on, real_send = wa.is_on, wa.send
linked = {"on": False}
wa.is_on = lambda: linked["on"]


def fake_send(number, text="", pdf=None, file_name="", timeout=60):
    sent.append({"number": number, "text": text, "pdf": pdf, "file_name": file_name})
    return "ok"


wa.send = fake_send
try:
    print()
    print("2. The employee form keeps a mobile number")
    r = cl.put("/api/employees/" + EID, json={"Phone": " 050 123 4567 "})
    check("saving a phone succeeds", r.status_code == 200, r.status_code)
    rows = cl.get("/api/employees").get_json()
    me = next((e for e in rows if e.get("_id") == EID), {})
    check("and it is stored, trimmed", me.get("Phone") == "050 123 4567", me.get("Phone"))
    r = cl.put("/api/employees/" + EID, json={"EmployeeName": "Wa Tester"})
    me = next((e for e in cl.get("/api/employees").get_json() if e.get("_id") == EID), {})
    check("an edit that does not mention it leaves it alone", me.get("Phone") == "050 123 4567", me.get("Phone"))

    print()
    print("3. Not linked: nothing is offered, and the refusal says why")
    j = cl.get("/api/assets/" + AID + "/sign/link").get_json()
    check("WhatsApp not offered", j.get("can_whatsapp") is False, j)
    check("because it is not linked", j.get("whatsapp_reason") == "not_linked", j.get("whatsapp_reason"))
    r = cl.post("/api/assets/" + AID + "/sign/send")
    check("sending is refused", r.status_code == 400, r.status_code)
    err = r.get_json().get("error") or ""
    check("naming both ways out", "email" in err.lower() and "WhatsApp" in err, err)
    check("nothing sent", not sent, len(sent))

    print()
    print("4. Linked, no email: the link goes on WhatsApp alone")
    linked["on"] = True
    j = cl.get("/api/assets/" + AID + "/sign/link").get_json()
    check("WhatsApp offered", j.get("can_whatsapp") is True, j)
    check("to the international number", j.get("assignee_phone") == "+971501234567", j.get("assignee_phone"))
    r = cl.post("/api/assets/" + AID + "/sign/send")
    check("the send succeeds", r.status_code == 200, r.get_json())
    j2 = r.get_json()
    check("one WhatsApp message", len(sent) == 1, len(sent))
    if sent:
        check("to the employee's number", sent[0]["number"] == "971501234567", sent[0]["number"])
        check("carrying the link the dialog shows", (j2.get("url") or "x") in sent[0]["text"], sent[0]["text"][:120])
        check("and naming the asset", "WhatsApp test laptop" in sent[0]["text"])
    check("reported as WhatsApp", "WhatsApp" in (j2.get("sent_to") or ""), j2.get("sent_to"))

    print()
    print("5. Switched off in Settings: not offered")
    r = cl.post("/api/whatsapp/settings", json={"country_code": "971", "send_link": False, "send_pdf": True})
    check("settings save", r.status_code == 200, r.status_code)
    j = cl.get("/api/assets/" + AID + "/sign/link").get_json()
    check("link on WhatsApp is off", j.get("can_whatsapp") is False and j.get("whatsapp_reason") == "off", j)
    r = cl.post("/api/whatsapp/settings", json={"country_code": "", "send_link": True})
    check("an empty country code is refused", r.status_code == 400, r.status_code)
    cl.post("/api/whatsapp/settings", json={"country_code": "971", "send_link": True, "send_pdf": True})

    print()
    print("6. Signing answers at once and the signed copy follows on WhatsApp")
    sent.clear()
    j = cl.get("/api/assets/" + AID + "/sign/link").get_json()
    from urllib.parse import urlparse
    tk = urlparse(j["url"]).path.rstrip("/").rsplit("/", 1)[-1]
    sig = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")
    t0 = time.time()
    r = cl.post("/api/assets/sign/approve", json={"token": tk, "name": "Wa Tester", "data": sig})
    took = time.time() - t0
    check("signing succeeds", r.status_code == 200, r.get_json())
    jj = r.get_json() or {}
    check("it says the copy is headed to WhatsApp", jj.get("whatsapp") is True, jj)
    check("and not to an email there is none of", jj.get("emailed") is False, jj)
    check("the answer does not wait for delivery", took < 5, f"{took:.2f}s")
    for _ in range(60):
        if sent: break
        time.sleep(0.25)
    check("the signed PDF went out", len(sent) == 1, len(sent))
    if sent:
        check("to the employee", sent[0]["number"] == "971501234567")
        check("as a PDF", (sent[0]["pdf"] or b"")[:4] == b"%PDF", (sent[0]["pdf"] or b"")[:8])
        check("named after the asset", sent[0]["file_name"] == "WA-1_signed.pdf", sent[0]["file_name"])

    print()
    print("7. The sign page shows the outcome where it can be seen")
    src = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
    check("the success banner has its own colours", "#result.ok{" in src)
    check("no reliance on the undefined --grn on that page", ".ok{color:var(--grn)}" not in src)
    check("the page scrolls to it", "res.scrollIntoView(" in src)
    check("the button is held while submitting", "sb.disabled=true; sb.textContent='⏳ SUBMITTING" in src)
    check("and released if it fails", "if(!j.ok){ sb.disabled=false;" in src)
    check("delivery runs on a thread", "target=_deliver_signed_asset_pdf" in src)

    print()
    print("8. It ships")
    df = open(os.path.join(ROOT, "Dockerfile"), encoding="utf-8").read()
    check("the image builds the bridge", "FROM node:22-bookworm-slim AS whatsapp" in df)
    check("and carries node + its modules", "COPY --from=whatsapp /usr/local/bin/node" in df
          and "COPY --from=whatsapp /wa/node_modules ./whatsapp/node_modules" in df)
    check("the lockfile is there to build from",
          os.path.exists(os.path.join(ROOT, "whatsapp", "package-lock.json")))
    idx = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    check("Settings has the WhatsApp card", 'id="waPanel"' in idx and 'id="waLinkBtn"' in idx)
    check("the employee form has the mobile field", 'id="e_Phone"' in idx)
finally:
    wa.is_on, wa.send = real_is_on, real_send
    c = A.conn(); cur = c.cursor()
    cur.execute("DELETE FROM Assets WHERE _id=%s", (AID,))
    cur.execute("DELETE FROM Employees WHERE _id=%s", (EID,))
    cur.execute("DELETE FROM AuditLog WHERE asset_id=%s", (AID,))
    cur.execute("UPDATE Settings SET smtp_host=%s, smtp_port=%s, smtp_user=%s, smtp_pass=%s, smtp_from=%s, "
                "wa_country_code=%s, wa_send_link=%s, wa_send_pdf=%s WHERE id=1",
                (before.get("smtp_host"), before.get("smtp_port"), before.get("smtp_user"),
                 before.get("smtp_pass"), before.get("smtp_from"),
                 before.get("wa_country_code") or "971",
                 1 if before.get("wa_send_link") is None else before.get("wa_send_link"),
                 1 if before.get("wa_send_pdf") is None else before.get("wa_send_pdf")))
    c.commit(); c.close()
    print()
    print("(test asset and employee removed, settings restored)")

print()
if fails:
    print("FAILED (%d): %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("ALL PASSED")
