"""Nothing but a person overwrites what a person typed.

This is the test for a report that took a while to believe: "recently added
position and employee details are changed to previous after update", and
"after update many users' job designation are empty". Two separate faults
producing one symptom, and both of them looked like the updater's fault
because they showed up after one.

1. The directory sync wrote EmployeeName, Designation, Department and Email
   unconditionally. Active Directory answers "" for an attribute a person
   does not have, so every sync emptied whatever had been typed into
   IT-Vault for everyone whose AD record has no title or department. The
   auto-sync runs every thirty minutes: work done in the afternoon was gone
   by the evening.

2. When AD *did* have an answer, it was usually the stale one -- which is why
   somebody typed over it in the first place -- and the sync put it back.
   Retyping did not help, because the next sync undid that too.

3. PUT /api/employees/<id> wrote all six columns from `data.get(col) or ""`,
   so any caller that sent only the field it changed cleared the other five.
   The web form sends the whole record so it never showed there; the phone
   app, an import and anything holding an API key do not.

The rule these three become: a field a person changes belongs to that person
and the sync stops writing it; a field nobody has touched is AD's to fill;
and an absent key is not an instruction to erase anything. Clearing a field
on purpose still works -- by sending "", which is a value, not a silence.
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
cl = A.app.test_client()
with cl.session_transaction() as s:
    s["user"] = "admin"
    s["role"] = "admin"

TAG = uuid.uuid4().hex[:6]
EMPID = "nb-" + TAG
RID = uuid.uuid4().hex


def row():
    c = A.conn(); cur = c.cursor()
    cur.execute("SELECT EmployeeName, Designation, Department, Email, manual_fields "
                "FROM Employees WHERE _id=%s", [RID])
    r = cur.fetchone(); c.close()
    return r or {}


def put(payload):
    return cl.put("/api/employees/" + RID, json=payload)


def sync_write(manual, name="", desig="", dept="", email=""):
    """What a directory sync would write, given what is already claimed."""
    return dict(A._ldap_fields_to_write(manual, (("EmployeeName", name),
                                                 ("Designation", desig),
                                                 ("Department", dept),
                                                 ("Email", email))))


c = A.conn(); cur = c.cursor()
cur.execute("""INSERT INTO Employees (_id, EmployeeID, EmpCode, EmployeeName, Designation,
                                      Department, Email, source)
               VALUES (%s,%s,%s,%s,%s,%s,%s,'ldap')""",
            (RID, EMPID, "NB-" + TAG, "Rashid Khan", "Site Supervisor",
             "Operations", "rashid@example.com"))
c.commit(); c.close()

try:
    print()
    print("1. A sync cannot write a field the directory has no answer for")
    # the exact shape of the bug: AD knows the name, has no title or department
    w = sync_write("", name="Rashid Khan", desig="", dept="", email="")
    check("an empty title is not written", "Designation" not in w, w)
    check("an empty department is not written", "Department" not in w, w)
    check("an empty email is not written", "Email" not in w, w)
    check("the name it does have is written", w.get("EmployeeName") == "Rashid Khan", w)
    check("whitespace counts as empty",
          "Designation" not in sync_write("", desig="   "),
          "a padded attribute is still no attribute")
    check("a sync with nothing to say writes nothing at all", sync_write("") == {})

    print()
    print("2. A field a person changed is not the directory's to change back")
    r = put({"Designation": "Operations Manager"})
    check("the change is accepted", r.status_code == 200, r.get_json())
    check("it is recorded as theirs", "designation" in (row().get("manual_fields") or "").lower(),
          row().get("manual_fields"))
    check("the response says which fields became theirs",
          (r.get_json() or {}).get("owned") == ["Designation"], r.get_json())
    # and now the sync, still holding AD's older title
    w = sync_write(row().get("manual_fields"), name="Rashid Khan",
                   desig="Site Supervisor", dept="Operations")
    check("AD's older title is refused", "Designation" not in w, w)
    check("but AD still owns the fields nobody touched",
          w.get("Department") == "Operations" and w.get("EmployeeName") == "Rashid Khan", w)

    print()
    print("3. Sending a field back unchanged does not claim it")
    # the web form posts the whole record every time; if that counted as an
    # edit, one save would freeze an employee against the directory for good
    put({"EmployeeName": "Rashid Khan", "Department": "Operations"})
    claimed = A._manual_set(row().get("manual_fields"))
    check("only the field that actually changed is claimed", claimed == {"designation"}, claimed)

    print()
    print("4. An absent key is not an instruction to erase")
    put({"EmployeeName": "Rashid A. Khan"})
    after = row()
    check("the designation survives", after["Designation"] == "Operations Manager", after)
    check("the department survives", after["Department"] == "Operations", after)
    check("the email survives", after["Email"] == "rashid@example.com", after)
    check("and the name did change", after["EmployeeName"] == "Rashid A. Khan", after)
    check("a PUT with no editable field at all changes nothing",
          (put({}).get_json() or {}).get("unchanged") is True)

    print()
    print("5. Clearing a field on purpose still works")
    put({"Department": ""})
    check("an explicit empty string is honoured", row()["Department"] == "", row())
    check("clearing is also an edit, so the field becomes theirs",
          "department" in A._manual_set(row().get("manual_fields")),
          "otherwise the next sync fills it straight back in")
    check("a cleared-on-purpose field is not refilled by AD",
          "Department" not in sync_write(row().get("manual_fields"), dept="Operations"))

    print()
    print("6. Every change is in the audit log, with what it was before")
    log = cl.get("/api/audit").get_json() or []
    mine = [e for e in log if e.get("action") == "EMPLOYEE_UPDATE"]
    check("the update is logged", bool(mine), "%d EMPLOYEE_UPDATE rows" % len(mine))
    detail = " | ".join(str(e.get("detail") or "") for e in mine[:6])
    check("the log names the field", "Designation" in detail, detail[:160])
    check("it records the value it had before", "Site Supervisor" in detail, detail[:160])
    check("and the value it was given", "Operations Manager" in detail, detail[:160])
    check("an emptied field reads as emptied, not as blank space",
          "(empty)" in detail, detail[:160])

    print()
    print("7. The record cannot be thrown away without a copy of it")
    src = io.open(os.path.join(ROOT, "app.py"), encoding="utf-8-sig").read()
    fn = src[src.index("def clear_audit_log("):]
    fn = fn[:fn.index("\n@app.route")]
    check("clearing the log takes a full backup first", '_run_backup("all")' in fn)
    check("and refuses to clear if that backup fails", "not clearing" in fn)
    check("the archive is named back to the caller", '"backup_file"' in fn)
    check("the clearing is itself logged", "AUDIT_LOG_CLEARED" in fn)

    print()
    print("8. The protection is stored, so it survives a restart and a restore")
    c = A.conn(); cur = c.cursor()
    cur.execute("SELECT COLUMN_NAME AS c FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='Employees' "
                "AND COLUMN_NAME='manual_fields'")
    check("manual_fields is a real column", cur.fetchone() is not None,
          "it has to outlive the process that set it")
    in_backup = {t.lower() for t in A._backup_tables(cur, "all")}
    c.close()
    check("Employees travels with a backup", "employees" in in_backup)
    check("so does the audit log", 'lines += _dump_section(cur, "AuditLog")' in src)
    check("and the sign links, added in this version", "signlinks" in in_backup,
          sorted(in_backup))

    print()
    print("9. The importer cannot reintroduce the pattern")
    # the one-off import inserts new rows; it must not UPDATE over existing ones
    imp = src[src.index("def ldap_import_employees("):]
    imp = imp[:imp.index("\ndef ldap_sync_all(")]
    check("the importer only inserts", "UPDATE Employees" not in imp)
    sync = src[src.index("def ldap_sync_all("):]
    sync = sync[:sync.index("\n@app.route")]
    check("the sync's only UPDATE goes through the rules",
          sync.count("UPDATE Employees SET") == 1
          and "_ldap_fields_to_write(" in sync, sync.count("UPDATE Employees SET"))
    check("it reads what is claimed before deciding",
          "SELECT _id, manual_fields FROM Employees" in sync)
    print()
    print("10. An asset behaves the same way")
    # The asset form had the identical fault, and more to lose: a status
    # update from the phone would have taken the serial number, the warranty
    # and the invoice reference with it.
    aid = "NB-" + TAG
    c = A.conn(); cur = c.cursor()
    cur.execute("""INSERT INTO Assets (_id, AssetTag, Name, Type, Status, Serial,
                                       WarrantyMonths, Note)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (aid, "NBA-" + TAG, "Blanking test laptop", "Laptop",
                 "Available", "SN-" + TAG, 36, "keep me"))
    c.commit(); c.close()
    try:
        r = cl.put("/api/assets/" + aid, json={"Status": "Under-Maintenance"})
        check("a one-field asset update is accepted", r.status_code == 200, r.get_json())
        c = A.conn(); cur = c.cursor()
        cur.execute("SELECT Name, Status, Serial, WarrantyMonths, Note FROM Assets WHERE _id=%s", [aid])
        a = cur.fetchone(); c.close()
        check("the status changed", a["Status"] == "Under-Maintenance", a)
        check("the name survives", a["Name"] == "Blanking test laptop", a)
        check("the serial survives", a["Serial"] == "SN-" + TAG, a)
        check("the warranty survives", int(a["WarrantyMonths"] or 0) == 36, a)
        check("the note survives", a["Note"] == "keep me", a)
        h = cl.get("/api/assets/" + aid + "/history").get_json() or []
        fields = {e.get("field") for e in h}
        check("the history records the field that changed", "Status" in fields, fields)
        check("and invents no others", fields == {"Status"}, fields)
    finally:
        c = A.conn(); cur = c.cursor()
        cur.execute("DELETE FROM History WHERE asset_id=%s", [aid])
        cur.execute("DELETE FROM Assets WHERE _id=%s", [aid])
        c.commit(); c.close()

finally:
    c = A.conn(); cur = c.cursor()
    cur.execute("DELETE FROM Employees WHERE _id=%s", [RID])

    cur.execute("DELETE FROM AuditLog WHERE action='EMPLOYEE_UPDATE' AND detail LIKE %s",
                ["%Operations Manager%"])
    c.commit(); c.close()
    print()
    print("(test employee and its log rows removed)")

print()
if fails:
    print("FAILED (%d): %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("ALL PASSED")
