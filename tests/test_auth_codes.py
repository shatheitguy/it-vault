"""A one-time code is not something the browser gets to read.

Flask's session is signed, not encrypted: whatever is put in it travels as
base64 in a cookie, and the holder of that cookie can decode it. Three secrets
used to live there.

The password reset code was the serious one. The cookie holding it belongs to
whoever *asked* for the reset, not to the account being reset -- so the attack
was: ask for a reset of `admin`, decode your own cookie, read the six digits,
post them back with a new password. The victim's mailbox never came into it.
Any account on the instance, including the only admin.

The emailed sign-in code had the same shape, which made "two factor" one
factor for anyone already holding a password. The TOTP secret being enrolled
was in there too -- your own secret, so not a breach, but not a thing to put
in a cookie either.

All three now live in AuthCodes as a peppered hash, and the session carries an
opaque handle worth nothing on its own. This test reads the actual cookie the
server sets and tries the actual attack.
"""

import base64
import io
import json
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

USER = "codetest-" + uuid.uuid4().hex[:6]
PW = "correct horse battery"
EMAIL = USER + "@example.com"

c = A.conn(); cur = c.cursor()
cur.execute("INSERT INTO Users (username, password, role, display, email) VALUES (%s,%s,%s,%s,%s)",
            (USER, A.hash_pw(PW), A.ROLE_ADMIN, "Code Test", EMAIL))
c.commit(); c.close()

# every code the server mints, captured as it is issued -- the only way a test
# can know a value that is deliberately never stored in full
ISSUED = []
_real_issue = A._issue_auth_code


def _spy(purpose, username, ttl_s, digits=6):
    handle, code = _real_issue(purpose, username, ttl_s, digits)
    ISSUED.append({"purpose": purpose, "username": username, "code": code, "handle": handle})
    return handle, code


A._issue_auth_code = _spy
# no SMTP in a test run, and the reset must not depend on one
A._send_password_reset_email = lambda *a, **k: True
A._send_simple_email = lambda *a, **k: True


def cookie_payload(client, resp=None):
    """What the browser can actually read out of its own session cookie.

    Read from the response's own Set-Cookie when there is one -- that is
    literally what went over the wire -- and fall back to the client's jar.
    """
    raw = ""
    if resp is not None:
        for h in resp.headers.getlist("Set-Cookie"):
            if h.startswith("session="):
                raw = h.split("=", 1)[1].split(";")[0]
                break
    if not raw:
        jar = client.get_cookie("session")
        if jar is None:
            return ""
        raw = jar.value
    # itsdangerous marks a zlib-compressed payload with a leading dot, so the
    # dot has to come off BEFORE splitting payload.timestamp.signature --
    # splitting first leaves an empty string, and a test that decodes nothing
    # passes every "the secret is not in here" check for the wrong reason.
    compressed = raw.startswith(".")
    if compressed:
        raw = raw[1:]
    body = raw.split(".")[0]
    pad = "=" * (-len(body) % 4)
    try:
        data = base64.urlsafe_b64decode(body + pad)
    except Exception:
        return raw
    if compressed or data[:1] == b"x":
        import zlib
        try:
            data = zlib.decompress(data)
        except Exception:
            pass
    return data.decode("utf-8", "replace")


def rows_for(purpose, username):
    c = A.conn(); cur = c.cursor()
    cur.execute("SELECT id, code_hash, payload, attempts FROM AuthCodes "
                "WHERE purpose=%s AND username=%s", (purpose, username))
    r = cur.fetchall(); c.close()
    return r


try:
    print()
    print("1. The attack: ask for someone else's reset, read your own cookie")
    attacker = A.app.test_client()
    r = attacker.post("/api/forgot-password/request", json={"username": USER})
    check("the request is accepted", r.status_code == 200, r.get_json())
    payload = cookie_payload(attacker, r)
    check("a reset was actually issued", any(i["purpose"] == "pwreset" for i in ISSUED),
          [i["purpose"] for i in ISSUED])
    code = [i for i in ISSUED if i["purpose"] == "pwreset"][-1]["code"]
    check("the code was emailed, not stored in the cookie",
          code not in payload,
          "cookie payload: " + payload[:120])
    # timestamps contain digit runs, so look at the values themselves rather
    # than at the text: nothing in here may BE a six-digit code
    try:
        vals = json.loads(payload)
    except Exception:
        vals = {}
    sixes = [k for k, v in vals.items() if isinstance(v, str) and re.fullmatch(r"\d{6}", v)]
    check("no value in the cookie is a six-digit code", not sixes, sixes)
    check("the cookie carries nothing but the handle and its clock",
          set(vals) <= {"_permanent", "pwreset_id", "pwreset_exp", "pwreset_sent_at"},
          sorted(vals))
    check("the username being reset is not in the cookie either",
          USER not in payload,
          "it named the account, which is half the attack")
    check("what IS in the cookie is an opaque handle",
          "pwreset_id" in payload, payload[:160])

    # the real attack, executed: try everything the cookie gives you
    guesses = re.findall(r"[A-Za-z0-9_\-]{4,}", payload)
    beaten = False
    for g in guesses[:40]:
        rr = attacker.post("/api/forgot-password/reset",
                           json={"code": g, "new_password": "attacker-pw-1234"})
        if rr.status_code == 200:
            beaten = True
            break
    check("nothing in the cookie can be used as the code", not beaten,
          "%d candidate strings tried" % min(len(guesses), 40))

    c = A.conn(); cur = c.cursor()
    cur.execute("SELECT password FROM Users WHERE username=%s", [USER])
    still = cur.fetchone()["password"]; c.close()
    check("the account's password is unchanged", A.verify_pw(PW, still),
          "this is the whole finding: takeover of any account, admin included")

    print()
    print("2. Only a hash is stored, and it is peppered")
    # a fresh one: the brute force above used the previous code's attempts up,
    # and a spent code leaves no row at all
    inspector = A.app.test_client()
    inspector.post("/api/forgot-password/request", json={"username": USER})
    code = [i for i in ISSUED if i["purpose"] == "pwreset"][-1]["code"]
    rows = rows_for("pwreset", USER)
    check("there is exactly one live row", len(rows) == 1, len(rows))
    if rows:
        stored = rows[0]["code_hash"]
        check("the code itself is not in the database", code not in stored)
        check("it is a sha256 hex digest", len(stored) == 64, len(stored))
        check("a bare sha256 of the code does not match it",
              stored != __import__("hashlib").sha256(code.encode()).hexdigest(),
              "six digits is a million-row lookup table without a pepper")
        check("the instance secret is what makes it match", stored == A._code_hash(code))

    print()
    print("3. Guessing is counted, and runs out")
    fresh = A.app.test_client()
    fresh.post("/api/forgot-password/request", json={"username": USER})
    real = [i for i in ISSUED if i["purpose"] == "pwreset"][-1]["code"]
    wrong = "000000" if real != "000000" else "111111"
    codes_seen = []
    for i in range(A.CODE_MAX_ATTEMPTS + 1):
        rr = fresh.post("/api/forgot-password/reset",
                        json={"code": wrong, "new_password": "nope-nope-nope"})
        codes_seen.append(rr.status_code)
    check("every wrong guess is refused", all(s in (401, 429) for s in codes_seen), codes_seen)
    last = fresh.post("/api/forgot-password/reset",
                      json={"code": real, "new_password": "nope-nope-nope"})
    check("and the real code is dead once the attempts run out",
          last.status_code != 200, last.get_json())
    check("the row is gone with it", not rows_for("pwreset", USER))

    print()
    print("4. The person who actually got the email can still reset")
    owner = A.app.test_client()
    owner.post("/api/forgot-password/request", json={"username": USER})
    real = [i for i in ISSUED if i["purpose"] == "pwreset"][-1]["code"]
    NEW = "brand-new-password-9"
    rr = owner.post("/api/forgot-password/reset", json={"code": real, "new_password": NEW})
    check("the reset succeeds", rr.status_code == 200, rr.get_json())
    c = A.conn(); cur = c.cursor()
    cur.execute("SELECT password FROM Users WHERE username=%s", [USER])
    now = cur.fetchone()["password"]; c.close()
    check("the password really changed", A.verify_pw(NEW, now))
    check("the code is single use", not rows_for("pwreset", USER))
    again = owner.post("/api/forgot-password/reset", json={"code": real, "new_password": "third-one"})
    check("replaying it fails", again.status_code != 200, again.get_json())
    # and the length rule cannot be dodged through this door -- checked
    # before the code is spent, so a refused password does not burn it
    short = A.app.test_client()
    short.post("/api/forgot-password/request", json={"username": USER})
    real2 = [i for i in ISSUED if i["purpose"] == "pwreset"][-1]["code"]
    rr2 = short.post("/api/forgot-password/reset", json={"code": real2, "new_password": "x"})
    check("a short new password is refused", "8 characters" in str(rr2.get_json()), rr2.get_json())
    rr3 = short.post("/api/forgot-password/reset", json={"code": real2, "new_password": "long-enough-1"})
    check("and the code still works afterwards", rr3.status_code == 200, rr3.get_json())
    NEW = "long-enough-1"          # the password the account actually has now

    print()
    print("5. The emailed sign-in code is not in the cookie either")
    c = A.conn(); cur = c.cursor()
    cur.execute("UPDATE Users SET email_otp_enabled=1 WHERE username=%s", [USER])
    c.commit(); c.close()
    cl2 = A.app.test_client()
    r = cl2.post("/api/login", json={"username": USER, "password": NEW})
    j = r.get_json() or {}
    check("login stops for a second factor", j.get("need_2fa") is True, j)
    payload2 = cookie_payload(cl2, r)
    otp = [i for i in ISSUED if i["purpose"] == "login2fa"]
    check("a sign-in code was issued", bool(otp))
    if otp:
        check("it is not in the cookie", otp[-1]["code"] not in payload2, payload2[:120])
    try:
        vals2 = json.loads(payload2)
    except Exception:
        vals2 = {}
    check("no value in the cookie is a six-digit code",
          not [k for k, v in vals2.items() if isinstance(v, str) and re.fullmatch(r"\d{6}", v)],
          sorted(vals2))
    check("the pending sign-in carries a handle, not a code",
          "pending_2fa_id" in vals2 and not any("code" in k for k in vals2),
          sorted(vals2))
    bad = cl2.post("/api/2fa/verify-login", json={"method": "email", "code": "000000"})
    check("a wrong code is refused", bad.status_code == 401, bad.get_json())
    if otp:
        good = cl2.post("/api/2fa/verify-login", json={"method": "email", "code": otp[-1]["code"]})
        check("the real one signs you in", good.status_code == 200, good.get_json())
        check("and it cannot be replayed",
              cl2.post("/api/2fa/verify-login",
                       json={"method": "email", "code": otp[-1]["code"]}).status_code != 200)

    print()
    print("6. The TOTP secret being enrolled stays on the server")
    cl3 = A.app.test_client()
    with cl3.session_transaction() as s:
        s["user"] = USER
        s["role"] = A.ROLE_ADMIN
    setup = cl3.post("/api/2fa/totp/setup").get_json() or {}
    secret = setup.get("secret") or ""
    check("setup returns a secret to show as a QR", len(secret) > 10)
    payload3 = cookie_payload(cl3)
    check("but the cookie does not carry it", secret not in payload3, payload3[:120])
    check("only a handle", "totp_enroll_id" in payload3, payload3[:160])
    import pyotp
    ok = cl3.post("/api/2fa/totp/confirm", json={"code": pyotp.TOTP(secret).now()})
    check("confirming with the app's code still works", ok.status_code == 200, ok.get_json())

    print()
    print("7. Expiry is the database's job, not the cookie's")
    handle, code7 = A._issue_auth_code("pwreset", USER, 600)
    c = A.conn(); cur = c.cursor()
    cur.execute("UPDATE AuthCodes SET expires_at = DATE_SUB(NOW(), INTERVAL 1 MINUTE) WHERE id=%s",
                [handle])
    c.commit(); c.close()
    who, err = A._check_auth_code(handle, "pwreset", code7)
    check("an expired code is refused", who is None and err, err)
    check("a code from another purpose is refused",
          A._check_auth_code(*( (lambda h, cd: (h, "login2fa", cd))(*A._issue_auth_code("pwreset", USER, 600)) ))[0] is None,
          "purposes must not be interchangeable")

    print()
    print("8. The source no longer puts any secret in the session")
    src = io.open(os.path.join(ROOT, "app.py"), encoding="utf-8-sig").read()
    leaks = re.findall(r'session\["[a-z_0-9]*(?:code|secret|pass)[a-z_0-9]*"\]\s*=', src)
    check("no code, secret or password is written to the session", not leaks, leaks)
    check("the store hashes what it keeps", "def _code_hash(" in src)
    check("and compares in constant time", "hmac.compare_digest" in src)
finally:
    A._issue_auth_code = _real_issue
    c = A.conn(); cur = c.cursor()
    cur.execute("DELETE FROM AuthCodes WHERE username=%s", [USER])
    cur.execute("DELETE FROM Users WHERE username=%s", [USER])
    c.commit(); c.close()
    print()
    print("(test account and its codes removed)")

print()
if fails:
    print("FAILED (%d): %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("ALL PASSED")
