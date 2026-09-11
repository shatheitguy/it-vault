import urllib.request, json, urllib.error, time

B = "http://127.0.0.1:5000"
TS = str(int(time.time()))  # unique suffix so the test is idempotent / re-runnable

def req(method, path, body=None, cookie=None):
    headers = {"Content-Type": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(B + path, data=data, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(r)
        return resp.status, resp.read().decode(), resp.headers.get("Set-Cookie")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(), None

def login(u, p):
    return req("POST", "/api/login", {"username": u, "password": p})

res = []
def check(name, cond, extra=""):
    res.append(("PASS" if cond else "FAIL", name, extra))

# 1. admin login
s, b, ck = login("admin", "admin123")
check("admin login", s == 200, b)
check("admin session cookie", bool(ck))

# 2. no-cookie assets -> 401
s2, _, _ = req("GET", "/api/assets")
check("no-cookie assets -> 401", s2 == 401)

# unique test users for this run
ED = "ed_" + TS
VW = "vw_" + TS

# 3. create editor + viewer
s, b, _ = req("POST", "/api/users", {"username": ED, "password": "edit123", "role": "read-write", "display": "Edit"}, ck)
check("create editor", s == 200, b)
s, b, _ = req("POST", "/api/users", {"username": VW, "password": "view123", "role": "read-only", "display": "View"}, ck)
check("create viewer", s == 200, b)

# 4. list users includes our two
s, b, _ = req("GET", "/api/users", cookie=ck)
us = json.loads(b)
check("list users includes editor+viewer", s == 200 and any(u["username"] == ED for u in us) and any(u["username"] == VW for u in us))

# 5. editor: add asset ok, user-mgmt forbidden
s, b, eck = login(ED, "edit123")
check("editor login", s == 200, b)
s, b, _ = req("POST", "/api/assets", {"Name": "Editor Asset", "Type": "Router", "Serial": "SN-ED-" + TS, "Status": "Active"}, eck)
check("editor add asset", s == 200, b)
s, b, _ = req("GET", "/api/users", cookie=eck)
check("editor user-mgmt -> 403", s == 403, b)

# 6. viewer: list ok, add forbidden, change own pw, re-login
s, b, vck = login(VW, "view123")
check("viewer login", s == 200, b)
s, b, _ = req("GET", "/api/assets", cookie=vck)
check("viewer list", s == 200)
s, b, _ = req("POST", "/api/assets", {"Name": "x"}, vck)
check("viewer add -> 403", s == 403, b)
s, b, _ = req("POST", "/api/profile/password", {"old": "view123", "new": "view999"}, vck)
check("viewer change own pw", s == 200, b)
s, b, _ = login(VW, "view999")
check("viewer login new pw", s == 200, b)

# 7. import sample + count
with open("C:/Users/Sha/asset-manager/sample-assets.xlsx", "rb") as f:
    raw = f.read()
boundary = "----itguytest"
bd = b"--" + boundary.encode() + b"\r\n"
bd += b'Content-Disposition: form-data; name="file"; filename="sample.xlsx"\r\n'
bd += b"Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n"
bd += raw + b"\r\n--" + boundary.encode() + b"--\r\n"
reqimp = urllib.request.Request(B + "/api/import", data=bd,
    headers={"Content-Type": "multipart/form-data; boundary=" + boundary, "Cookie": eck}, method="POST")
r = urllib.request.urlopen(reqimp); ib = r.read().decode()
check("import sample", r.status == 200, ib)

s, b, _ = req("GET", "/api/assets", cookie=ck)
assets = json.loads(b)
check("assets count > 10", s == 200 and len(assets) >= 10, "count=" + str(len(assets)))

# 8. last-admin protection
s, b, _ = req("PUT", "/api/users/admin", {"role": "read-only"}, ck)
check("demote last admin -> 403", s == 403, b)

# 9. cleanup created test users (admin only)
req("DELETE", "/api/users/" + ED, cookie=ck)
req("DELETE", "/api/users/" + VW, cookie=ck)

for st, nm, ex in res:
    print(f"{st}  {nm}  {ex}")

fails = [r for r in res if r[0] == "FAIL"]
print(f"\nSUMMARY: {len(res)-len(fails)} PASS / {len(fails)} FAIL  (run {TS})")
