"""The signature is always black, and an asset tag shows the employee NUMBER.

Both were pulling something theme- or username-derived: the signature took the
accent colour, and the tag printed Employees.EmployeeID, which for anything
synced from AD is the login name.
"""
import io
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
cl = A.app.test_client()
with cl.session_transaction() as s:
    s["user"] = "admin"
    s["role"] = "admin"

print("1. The signature pad is black ink on a white pad")
# the sign page is only served with a valid token, so mint one the way the app does
c = A.conn(); cur = c.cursor()
aid = "SIGTEST-" + uuid.uuid4().hex[:6]
cur.execute("INSERT INTO Assets (_id, AssetTag, Name, Type, Status) VALUES (%s,%s,%s,%s,%s)",
            (aid, "SIG-1", "Signature test", "Laptop", "Available"))
c.commit(); c.close()
tok = A._sign_token(aid) if hasattr(A, "_sign_token") else None
page = None
if tok:
    r = cl.get(f"/sign?token={tok}")
    page = r.get_data(as_text=True) if r.status_code == 200 else None
if page is None:
    # fall back to reading the template out of the module, which is what is served
    src = io.open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
    i = src.index("#sigCanvas{")
    page = src[i - 4000:i + 6000]

check("the pen is pure black", "SIG_INK='#000000'" in page, "SIG_INK not found")
check("nothing reads the accent for the pen", "accentColor()" not in page)
check("strokeStyle uses it", "ctx.strokeStyle = SIG_INK;" in page)
m = re.search(r"#sigCanvas\{[^}]*\}", page)
check("the pad itself is white", bool(m) and "background:#ffffff" in m.group(0),
      m.group(0)[:110] if m else "no rule")
m2 = re.search(r"#sigPlaceholder\{[^}]*\}", page)
check("and so is the placeholder", bool(m2) and "background:#ffffff" in m2.group(0),
      m2.group(0)[:110] if m2 else "no rule")
# an actual CALL, not the word in the comment explaining why there isn't one
check("the exported buffer is still transparent (nothing painted into it)",
      not re.search(r"ctx\.fillRect\s*\(", page),
      "a fill would box the signature on the PDF")

# A transparent PNG shows whatever it is dropped onto. The VIEW SIGNATURE
# popups used to write a bare <img> into a blank window, so black ink landed
# on the browser's own default background -- dark, in dark mode -- and the
# signature came out looking like anything but black.
src_all = io.open(os.path.join(ROOT, "app.py"), encoding="utf-8").read()
popups = re.findall(r"w\.document\.write\((.{0,400}?)\);", src_all, re.S)
check("all three VIEW SIGNATURE popups found", len(popups) == 3, len(popups))
for i, p in enumerate(popups, 1):
    check(f"popup {i} puts the signature on a white sheet", "background:#fff" in p,
          p[:80])
    check(f"popup {i} pins the light colour scheme", "color-scheme:light" in p,
          "otherwise a dark-mode browser darkens the sheet")
check("no popup writes a bare img onto an unstyled page",
      not re.search(r"w\.document\.write\('<img", src_all))

print("\n2. An asset tag prints the employee NUMBER, not the AD username")
c = A.conn(); cur = c.cursor()
emp_id = "j.smith"                      # what AD sync stores
cur.execute("DELETE FROM Employees WHERE EmployeeID=%s", [emp_id])
cur.execute("INSERT INTO Employees (_id, EmployeeID, EmpCode, EmployeeName, Department, source) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (uuid.uuid4().hex[:12], emp_id, "EMP-777", "John Smith", "IT", "test"))
cur.execute("UPDATE Assets SET EmployeeID=%s WHERE _id=%s", (emp_id, aid))
cur.execute("UPDATE Settings SET qr_fields=%s WHERE id=1",
            ["Name,AssetID,Type,Serial,EmployeeID,EmployeeName"])
c.commit(); c.close()

emap = A._employee_label_map()
check("the lookup map is built", emp_id in emap, list(emap)[:3])
code, name = A._employee_for_label(emap, emp_id)
check("id resolves to the employee number", code == "EMP-777", code)
check("name resolves to the person", name == "John Smith", name)

r = cl.get(f"/label/{aid}")
html = r.get_data(as_text=True)
check("the label renders", r.status_code == 200, r.status_code)
check("it prints EMP-777", "EMP-777" in html)
check("it does NOT print the AD username", emp_id not in html,
      "the login name is still on the tag")
check("the name is available as its own field", "John Smith" in html)

print("\n3. The bulk sheet agrees with the single label")
r = cl.get(f"/labels?ids={aid}")
bulk = r.get_data(as_text=True)
check("the sheet renders", r.status_code == 200, r.status_code)
check("it prints EMP-777 too", "EMP-777" in bulk)
check("and not the username", emp_id not in bulk)

print("\n4. An asset assigned to someone since deleted still says something")
c = A.conn(); cur = c.cursor()
cur.execute("DELETE FROM Employees WHERE EmployeeID=%s", [emp_id])
c.commit(); c.close()
code, name = A._employee_for_label(A._employee_label_map(), emp_id)
check("falls back to the stored value", code == emp_id and name == emp_id, f"{code!r}/{name!r}")
r = cl.get(f"/label/{aid}")
check("and the tag still renders", r.status_code == 200, r.status_code)

print("\n5. An unassigned asset prints nothing for it")
code, name = A._employee_for_label(A._employee_label_map(), "")
check("blank in, blank out", code == "" and name == "", f"{code!r}/{name!r}")

c = A.conn(); cur = c.cursor()
cur.execute("DELETE FROM Assets WHERE _id=%s", [aid])
cur.execute("UPDATE Settings SET qr_fields=%s WHERE id=1",
            ["Name,AssetID,Type,Serial,Status,Location"])
c.commit(); c.close()
print("\n(test asset and employee removed, label fields restored)")
print("\n" + ("ALL PASSED" if not fails else f"{len(fails)} FAILED: " + "; ".join(fails)))
raise SystemExit(1 if fails else 0)
