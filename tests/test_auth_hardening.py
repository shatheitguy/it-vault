"""Passwords, login attempts, signatures and cookies.

Four things that were each a single line away from being a bad day, checked
by exercising them rather than by reading them.

  * A password hash has to be slow. One round of salted SHA-256 is what a
    cracking rig eats; PBKDF2 at 600k rounds makes each guess cost about a
    millisecond. Existing hashes still have to verify, or upgrading the app
    locks everyone out of their own system.
  * A login form with no limit is an offer. Ten wrong passwords in fifteen
    minutes and that address waits.
  * A signature is somebody's handwriting. It sat behind a bare login check,
    which is any account at all -- including an API key handed to an agent
    for reading tickets.
  * A session cookie without Secure travels in clear over HTTP. It cannot
    simply be switched on -- most of these installs are plain HTTP on a LAN,
    where a Secure cookie is never sent and nobody can log in -- so it is
    decided per request, and that decision is what this checks.
"""

import os
import sys
import time
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

PW = "correct horse battery staple " + uuid.uuid4().hex[:6]
USER = "sec-test-" + uuid.uuid4().hex[:8]

print("\nhow a password is stored")
h = A.hash_pw(PW)
check("it is PBKDF2, not a bare digest", h.startswith("pbkdf2_sha256$"), h[:28])
check("the work factor travels with it", int(h.split("$")[1]) >= 600_000, h.split("$")[1])
check("the salt is per-password", A.hash_pw(PW).split("$")[2] != h.split("$")[2])
check("the right password verifies", A.verify_pw(PW, h))
check("a wrong one does not", not A.verify_pw(PW + "x", h))
check("rubbish in the column does not crash it", A.verify_pw(PW, "") is False
      and A.verify_pw(PW, "nonsense") is False)

t0 = time.time()
A.verify_pw(PW, h)
cost_ms = (time.time() - t0) * 1000
check("a single guess costs real time", cost_ms > 20,
      "%.0f ms per attempt -- a fast hash would be ~0.001 ms" % cost_ms)

print("\nand the hashes that already exist")
legacy = A.hashlib.sha256(("abcd1234" + PW).encode()).hexdigest()
legacy = "abcd1234$" + legacy
check("a legacy hash still verifies", A.verify_pw(PW, legacy),
      "otherwise upgrading locks every existing user out")
check("a legacy hash is flagged for replacement", A.needs_rehash(legacy))
check("a current hash is not", not A.needs_rehash(h))
check("a weaker PBKDF2 hash is", A.needs_rehash(A.hash_pw(PW, rounds=1000)),
      "so raising the round count upgrades the estate as people sign in")

# ---- a real user, for the login paths
c = A.conn(); cur = c.cursor()
cur.execute("INSERT INTO Users (username, password, role, display, email) VALUES (%s,%s,%s,%s,%s)",
            (USER, legacy, A.ROLE_ADMIN, "Security test", ""))
c.commit(); c.close()

try:
    print("\nsigning in upgrades the stored hash")
    A._LOGIN_HITS.clear()
    cl = A.app.test_client()
    r = cl.post("/api/login", json={"username": USER, "password": PW})
    check("the login succeeds on the old hash", r.status_code == 200, r.status_code)
    c = A.conn(); cur = c.cursor()
    cur.execute("SELECT password FROM Users WHERE username=%s", [USER])
    after = (cur.fetchone() or {}).get("password", ""); c.close()
    check("and the hash is rewritten as PBKDF2", after.startswith("pbkdf2_sha256$"), after[:22])
    check("the same password still works afterwards", A.verify_pw(PW, after))

    print("\nguessing is rate limited")
    A._LOGIN_HITS.clear()
    codes = []
    for _ in range(A.LOGIN_MAX_ATTEMPTS + 2):
        codes.append(A.app.test_client().post(
            "/api/login", json={"username": USER, "password": "wrong"}).status_code)
    check("wrong passwords are refused", codes[0] == 401, codes[0])
    check("and eventually throttled", 429 in codes,
          "first 429 at attempt %s of %s" % (codes.index(429) + 1 if 429 in codes else "-",
                                             len(codes)))
    check("the limit is what we think it is", codes.count(401) == A.LOGIN_MAX_ATTEMPTS,
          "%d refusals before the gate closed" % codes.count(401))
    r = A.app.test_client().post("/api/login", json={"username": USER, "password": PW})
    check("a throttled address cannot get in with the right password either",
          r.status_code == 429, r.status_code)

    print("\nand a correct password clears the count")
    A._LOGIN_HITS.clear()
    for _ in range(3):
        A.app.test_client().post("/api/login", json={"username": USER, "password": "wrong"})
    A.app.test_client().post("/api/login", json={"username": USER, "password": PW})
    hits = sum(len(v) for k, v in A._LOGIN_HITS.items() if USER.lower() in k)
    check("someone who mistypes then gets it right is not half locked out",
          hits == 0, "%d attempts still counted" % hits)

    print("\nthe signature endpoint")
    src = open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
    block = src[src.index('@app.route("/api/assets/<aid>/signature")'):][:400]
    check("asks for assets read, not merely a login",
          'module="assets", level="read"' in block,
          "a bare @auth_required() lets any account read anyone's handwriting")

    anon = A.app.test_client()
    r = anon.get("/api/assets/whatever/signature")
    check("and a stranger gets nothing", r.status_code in (401, 403, 302), r.status_code)

    print("\ncookies")
    A._LOGIN_HITS.clear()
    plain = A.app.test_client().post("/api/login", json={"username": USER, "password": PW})
    set_plain = " ".join(plain.headers.getlist("Set-Cookie"))
    check("plain HTTP keeps working (no Secure, or nobody can sign in on a LAN)",
          "Secure" not in set_plain, set_plain[:60])
    A._LOGIN_HITS.clear()
    tls = A.app.test_client().post("/api/login", json={"username": USER, "password": PW},
                                   headers={"X-Forwarded-Proto": "https"})
    set_tls = " ".join(tls.headers.getlist("Set-Cookie"))
    check("behind TLS the session cookie is Secure", "Secure" in set_tls, set_tls[:80])
    check("it is still HttpOnly and SameSite", "HttpOnly" in set_tls and "SameSite" in set_tls)

    print("\nthe acknowledgement link's signature")
    tk = A._sign_token({"asset_id": "abc", "n": "deadbeef"}, exp_hours=1)
    sig = tk.rsplit(".", 1)[1]
    check("is the whole digest, not a truncation", len(sig) == 64, "%d chars" % len(sig))
    check("and verifies", (A._verify_token(tk) or {}).get("asset_id") == "abc")
    check("a tampered payload does not", A._verify_token("x" + tk) is None)
    legacy_tk = tk.rsplit(".", 1)[0] + "." + sig[:16]
    check("a link already in somebody's inbox still works",
          (A._verify_token(legacy_tk) or {}).get("asset_id") == "abc",
          "16-character tags stay valid until they expire")
    check("but a wrong short tag does not",
          A._verify_token(tk.rsplit(".", 1)[0] + "." + "0" * 16) is None)
finally:
    A._LOGIN_HITS.clear()
    c = A.conn(); cur = c.cursor()
    cur.execute("DELETE FROM Users WHERE username=%s", [USER])
    c.commit(); c.close()
    print("\n(test user removed)")

print()
if fails:
    print("FAILED (%d): %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("ALL PASSED")
