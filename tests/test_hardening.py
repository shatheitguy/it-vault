"""The rest of the audit, held in place.

One test per finding, each driving the real thing rather than reading the
source where it can:

  M1  an uploaded invoice is a download with a fixed type, and a file whose
      body is not what its name claims is refused at upload
  M2  a request body has a ceiling
  M3  a backup is every credential in one file, so only an admin may take one
  M4  API keys are stored as hashes and shown once
  M5  X-Forwarded-For is a claim, not an address
  M6  every response carries the headers that stand behind an escaping slip
  M7  guessing signature codes runs out
  M8  the label pages are behind the same gate as the page showing the same data
  M9  dependencies have ceilings
  M10 a signature is an image, and a bounded one
  L4  a monitor cannot be pointed at cloud instance metadata
"""

import io
import os
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
SRC = io.open(os.path.join(ROOT, "app.py"), encoding="utf-8-sig").read()

admin = A.app.test_client()
with admin.session_transaction() as s:
    s["user"] = "admin"
    s["role"] = "admin"
anon = A.app.test_client()

AID = "hard-" + uuid.uuid4().hex[:8]
c = A.conn(); cur = c.cursor()
cur.execute("INSERT INTO Assets (_id, AssetTag, Name, Type, Status) VALUES (%s,%s,%s,%s,%s)",
            (AID, "HD-" + uuid.uuid4().hex[:4].upper(), "Hardening test", "Laptop", "Available"))
c.commit(); c.close()

PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
       b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
       b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")
HTML_AS_GIF = b"<html><script>alert(1)</script></html>"

try:
    print()
    print("M1. An invoice is a download, not a page")
    r = admin.post("/api/assets/%s/invoice" % AID,
                   data={"file": (io.BytesIO(HTML_AS_GIF), "invoice.gif")},
                   content_type="multipart/form-data")
    check("a file whose body is not an image is refused", r.status_code == 400, r.get_json())
    r = admin.post("/api/assets/%s/invoice" % AID,
                   data={"file": (io.BytesIO(b"not a pdf at all"), "invoice.pdf")},
                   content_type="multipart/form-data")
    check("and neither is an invented PDF", r.status_code == 400, r.get_json())
    r = admin.post("/api/assets/%s/invoice" % AID,
                   data={"file": (io.BytesIO(PDF), "invoice.pdf")},
                   content_type="multipart/form-data")
    fname = (r.get_json() or {}).get("file")
    check("a real PDF is accepted", r.status_code == 200 and bool(fname), r.get_json())
    if fname:
        d = admin.get("/invoice/" + fname)
        disp = d.headers.get("Content-Disposition", "")
        check("it comes back as an attachment", "attachment" in disp, disp)
        check("with sniffing switched off",
              d.headers.get("X-Content-Type-Options") == "nosniff",
              d.headers.get("X-Content-Type-Options"))
        check("and a policy that lets it do nothing",
              "default-src 'none'" in (d.headers.get("Content-Security-Policy") or ""),
              d.headers.get("Content-Security-Policy"))

    print()
    print("M2. A request body has a ceiling")
    cap = A.app.config.get("MAX_CONTENT_LENGTH")
    check("there is a limit at all", bool(cap), cap)
    check("and it is a sane size", 8 * 1024 * 1024 <= (cap or 0) <= 256 * 1024 * 1024,
          "%s bytes" % cap)

    print()
    print("M3. A backup is every credential in one file")
    staff = A.app.test_client()
    with staff.session_transaction() as s:
        s["user"] = "someone"
        s["role"] = "staff"
    r = staff.get("/api/backup?scope=all")
    check("a non-admin cannot download one", r.status_code in (401, 403), r.status_code)
    fn = SRC[SRC.index("def backup():"):]
    fn = fn[:fn.index("\n@app.route")]
    check("the reason is written next to the route", "password hash" in fn)

    print()
    print("M4. API keys are hashes")
    c = A.conn(); cur = c.cursor()
    cur.execute("SELECT username, api_key FROM Users WHERE api_key<>''")
    stored = cur.fetchall(); c.close()
    check("nothing stored is a raw key",
          all(len(r["api_key"]) == 64 for r in stored),
          [(r["username"], len(r["api_key"])) for r in stored])
    r = admin.post("/api/profile/apikey")
    j = r.get_json() or {}
    key = j.get("api_key") or ""
    check("generating one returns the key once", len(key) == 48, len(key))
    check("and says it will not be shown again", "not shown again" in (j.get("note") or "").lower(),
          j.get("note"))
    c = A.conn(); cur = c.cursor()
    cur.execute("SELECT api_key FROM Users WHERE username='admin'")
    row = cur.fetchone() or {}; c.close()
    check("what is stored is the hash of it", row.get("api_key") == A._api_key_hash(key))
    check("the key itself is not in the database", row.get("api_key") != key)
    prof = admin.get("/api/profile").get_json() or {}
    check("the profile says a key exists, not what it is",
          prof.get("api_key_set") is True and "api_key" not in prof, sorted(prof))
    # and the key still works as a credential
    fresh = A.app.test_client()
    r = fresh.get("/api/assets", headers={"X-Api-Key": key})
    check("the returned key authenticates", r.status_code == 200, r.status_code)
    r = fresh.get("/api/assets", headers={"X-Api-Key": key[:-1] + "0"})
    check("a wrong one does not", r.status_code in (401, 403), r.status_code)

    print()
    print("M5. X-Forwarded-For is a claim, not an address")
    with A.app.test_request_context("/", headers={"X-Forwarded-For": "8.8.8.8"},
                                    environ_base={"REMOTE_ADDR": "203.0.113.9"}):
        check("an untrusted peer cannot rewrite its address",
              A._client_ip() == "203.0.113.9", A._client_ip())
    A.TRUSTED_PROXIES.append("203.0.113.9")
    try:
        with A.app.test_request_context("/", headers={"X-Forwarded-For": "8.8.8.8"},
                                        environ_base={"REMOTE_ADDR": "203.0.113.9"}):
            check("a named proxy can", A._client_ip() == "8.8.8.8", A._client_ip())
    finally:
        A.TRUSTED_PROXIES.remove("203.0.113.9")

    print()
    print("M6. Headers stand behind an escaping slip")
    h = anon.get("/portal").headers
    check("nosniff", h.get("X-Content-Type-Options") == "nosniff")
    check("the app cannot be framed from elsewhere",
          h.get("X-Frame-Options") == "SAMEORIGIN", h.get("X-Frame-Options"))
    csp = h.get("Content-Security-Policy") or ""
    check("there is a policy", bool(csp), csp[:60])
    check("it forbids objects", "object-src 'none'" in csp)
    check("it pins where forms may post", "form-action 'self'" in csp)
    check("and who may frame it", "frame-ancestors 'self'" in csp)
    check("a referrer policy is set", bool(h.get("Referrer-Policy")), h.get("Referrer-Policy"))

    print()
    print("M7. Guessing a signature code runs out")
    A._PUBLIC_HITS.clear() if hasattr(A, "_PUBLIC_HITS") else None
    codes = [anon.get("/api/assets/sign/verify?token=zzzz%d" % i).status_code for i in range(70)]
    check("the attempts are counted", 429 in codes,
          "%d refusals, last=%s" % (codes.count(429), codes[-1]))

    print()
    print("M8. The label pages are behind the same gate as the record")
    check("a single label needs an account",
          anon.get("/label/" + AID).status_code in (401, 403),
          anon.get("/label/" + AID).status_code)
    check("so does a sheet",
          anon.get("/labels?ids=" + AID).status_code in (401, 403),
          anon.get("/labels?ids=" + AID).status_code)
    check("and staff can still print one", admin.get("/label/" + AID).status_code == 200)

    print()
    print("M9. Dependencies have ceilings")
    req = io.open(os.path.join(ROOT, "requirements.txt"), encoding="utf-8").read()
    pkgs = [l.strip() for l in req.splitlines()
            if l.strip() and not l.strip().startswith("#")]
    loose = [p for p in pkgs if "<" not in p and "==" not in p]
    check("every dependency is bounded", not loose, loose)
    check("and there are still all of them", len(pkgs) >= 14, len(pkgs))

    print()
    print("M10. A signature is an image, and a bounded one")
    with A.app.test_request_context("http://itvault.example/"):
        _tk, url = A._issue_sign_link(AID, "Hardening")
    code = url.rsplit("/", 1)[-1]
    A._PUBLIC_HITS.clear() if hasattr(A, "_PUBLIC_HITS") else None
    r = anon.post("/api/assets/sign/approve",
                  json={"token": code, "name": "Someone", "data": "not-an-image"})
    check("a signature that is not an image is refused", r.status_code == 400, r.get_json())
    r = anon.post("/api/assets/sign/approve",
                  json={"token": code, "name": "Someone",
                        "data": "data:image/png;base64," + "A" * 400000})
    check("and an enormous one too", r.status_code == 400, r.get_json())

    print()
    print("L4. A monitor cannot read this host's own credentials")
    for target in ("169.254.169.254", "http://169.254.169.254/latest/meta-data/",
                   "metadata.google.internal", "169.254.169.254:80"):
        ok, why = A._monitor_target_allowed(target)
        check("refused: %s" % target, not ok, why[:60])
    for target in ("192.168.1.10", "https://status.example.com", "10.0.0.5:8080"):
        ok, _ = A._monitor_target_allowed(target)
        check("allowed: %s" % target, ok)
finally:
    c = A.conn(); cur = c.cursor()
    cur.execute("SELECT InvoiceFile FROM Assets WHERE _id=%s", [AID])
    row = cur.fetchone() or {}
    cur.execute("DELETE FROM SignLinks WHERE asset_id=%s", [AID])
    cur.execute("DELETE FROM Assets WHERE _id=%s", [AID])
    c.commit(); c.close()
    if row.get("InvoiceFile"):
        try:
            os.remove(os.path.join(A.INVOICE_DIR, row["InvoiceFile"]))
        except Exception:
            pass
    print()
    print("(test asset and its upload removed)")

print()
if fails:
    print("FAILED (%d): %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("ALL PASSED")
