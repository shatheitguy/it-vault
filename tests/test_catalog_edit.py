"""A catalogue entry can be corrected, not only destroyed.

The Product Catalog offered one button per row: DEL. So fixing a typo meant
deleting the entry and adding it again — and that is worse than it sounds,
because assets do not point at these lists by id. They carry the name as
text, which is what makes an exported sheet readable and an import possible.

Delete-and-re-add therefore left every asset still spelling it the old way,
with the old spelling no longer in the dropdown: open such an asset, save it,
and the value silently becomes whatever was selected instead.

So a rename updates the records that carry the name. That is the whole point
of the feature, and it is what this test is about.
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
CAT_OLD, CAT_NEW = "Cat-" + TAG, "Category " + TAG
MFR_OLD, MFR_NEW = "Mfr-" + TAG, "Maker " + TAG
MOD_OLD, MOD_NEW = "Mod-" + TAG, "Model " + TAG
CT_OLD, CT_NEW = "CT-" + TAG, "Contract type " + TAG
AID = "cat-" + uuid.uuid4().hex[:8]
made = []


def add(kind, payload):
    r = cl.post("/api/" + kind, json=payload)
    return r.status_code == 200


def listing(kind):
    return cl.get("/api/" + kind).get_json() or []


def find(kind, name):
    return next((x for x in listing(kind) if x["name"] == name), None)


def asset_row():
    c = A.conn(); cur = c.cursor()
    cur.execute("SELECT Type, Manufacturer, Model FROM Assets WHERE _id=%s", [AID])
    r = cur.fetchone(); c.close()
    return r or {}


try:
    print()
    print("1. Set up: a category, a maker, a model and an asset using all three")
    check("category added", add("categories", {"name": CAT_OLD}))
    check("manufacturer added", add("manufacturers", {"name": MFR_OLD}))
    mfr = find("manufacturers", MFR_OLD)
    check("model added", add("models", {"name": MOD_OLD,
                                        "manufacturer_id": mfr and mfr["id"]}))
    check("contract type added", add("contract-types", {"name": CT_OLD}))
    c = A.conn(); cur = c.cursor()
    cur.execute("""INSERT INTO Assets (_id, AssetTag, Name, Type, Manufacturer, Model, Status)
                   VALUES (%s,%s,%s,%s,%s,%s,'Available')""",
                (AID, "CE-" + TAG, "Catalogue edit test", CAT_OLD, MFR_OLD, MOD_OLD))
    cur.execute("INSERT INTO Contracts (name, vendor, type) VALUES (%s,%s,%s)",
                ("Contract " + TAG, "Vendor", CT_OLD))
    c.commit(); c.close()
    check("an asset carries all three as text",
          asset_row() == {"Type": CAT_OLD, "Manufacturer": MFR_OLD, "Model": MOD_OLD},
          asset_row())

    print()
    print("2. Renaming a category carries through to the assets in it")
    cat = find("categories", CAT_OLD)
    r = cl.put("/api/categories", json={"id": cat["id"], "name": CAT_NEW})
    j = r.get_json() or {}
    check("the rename is accepted", r.status_code == 200, j)
    check("it reports what it touched", j.get("updated", 0) >= 1, j)
    check("the list shows the new name", find("categories", CAT_NEW) is not None)
    check("and not the old one", find("categories", CAT_OLD) is None)
    check("the asset moved with it", asset_row()["Type"] == CAT_NEW, asset_row())

    print()
    print("3. Same for a manufacturer and a model")
    r = cl.put("/api/manufacturers", json={"id": mfr["id"], "name": MFR_NEW})
    check("the manufacturer is renamed", r.status_code == 200, r.get_json())
    check("the asset's manufacturer followed", asset_row()["Manufacturer"] == MFR_NEW,
          asset_row())
    mod = find("models", MOD_OLD)
    r = cl.put("/api/models", json={"id": mod["id"], "name": MOD_NEW})
    check("the model is renamed", r.status_code == 200, r.get_json())
    check("the asset's model followed", asset_row()["Model"] == MOD_NEW, asset_row())

    print()
    print("4. A model can change maker, and that does not rewrite assets")
    check("a second maker exists", add("manufacturers", {"name": "Other " + TAG}))
    other = find("manufacturers", "Other " + TAG)
    mod = find("models", MOD_NEW)
    r = cl.put("/api/models", json={"id": mod["id"], "name": MOD_NEW,
                                    "manufacturer_id": other["id"]})
    check("the move is accepted", r.status_code == 200, r.get_json())
    moved = find("models", MOD_NEW)
    check("the catalogue shows the new maker",
          moved and moved.get("manufacturer") == "Other " + TAG, moved)
    check("the asset keeps the maker it was saved with",
          asset_row()["Manufacturer"] == MFR_NEW,
          "a model moving in the catalogue is a correction, not asset history")

    print()
    print("5. A contract type renames its contracts")
    ct = find("contract-types", CT_OLD)
    r = cl.put("/api/contract-types", json={"id": ct["id"], "name": CT_NEW})
    check("the rename is accepted", r.status_code == 200, r.get_json())
    c = A.conn(); cur = c.cursor()
    cur.execute("SELECT type FROM Contracts WHERE name=%s", ["Contract " + TAG])
    row = cur.fetchone() or {}; c.close()
    check("the contract followed", row.get("type") == CT_NEW, row)

    print()
    print("6. The things it must refuse")
    cat = find("categories", CAT_NEW)
    r = cl.put("/api/categories", json={"id": cat["id"], "name": "   "})
    check("an empty name", r.status_code == 400, r.get_json())
    check("a name that is already taken",
          cl.put("/api/manufacturers",
                 json={"id": mfr["id"], "name": "Other " + TAG}).status_code == 400,
          "the lists are unique, and a clash should say so rather than 500")
    check("an entry that is gone",
          cl.put("/api/categories", json={"id": 99999999, "name": "x"}).status_code == 400)
    check("a request with no id",
          cl.put("/api/categories", json={"name": "x"}).status_code == 400)
    check("renaming to the same name is a no-op, not an error",
          cl.put("/api/categories", json={"id": cat["id"], "name": CAT_NEW}).status_code == 200)

    print()
    print("7. Who may do it")
    anon = A.app.test_client()
    check("not a visitor",
          anon.put("/api/categories", json={"id": cat["id"], "name": "x"}).status_code in (401, 403),
          anon.put("/api/categories", json={"id": cat["id"], "name": "x"}).status_code)
    viewer = A.app.test_client()
    with viewer.session_transaction() as s:
        s["user"] = "viewer-" + TAG
        s["role"] = "viewer"
    check("not a read-only role",
          viewer.put("/api/categories", json={"id": cat["id"], "name": "x"}).status_code in (401, 403),
          viewer.put("/api/categories", json={"id": cat["id"], "name": "x"}).status_code)

    print()
    print("8. It is in the log, because it rewrote other records")
    log = cl.get("/api/audit").get_json() or []
    mine = [e for e in log if e.get("action") == "CATALOG_RENAME"]
    detail = " | ".join(str(e.get("detail") or "") for e in mine[:8])
    check("the rename is logged", bool(mine), "%d rows" % len(mine))
    check("it says what it was called", CAT_OLD in detail, detail[:200])
    check("and what it is called now", CAT_NEW in detail, detail[:200])
    check("and how many records moved", "updated" in detail, detail[:200])

    print()
    print("9. The page offers it")
    html = io.open(os.path.join(ROOT, "index.html"), encoding="utf-8-sig").read()
    js = io.open(os.path.join(ROOT, "app.js"), encoding="utf-8-sig").read()
    check("there is a rename dialog", 'id="catEditModal"' in html)
    check("with a name field and a maker picker",
          'id="catEditName"' in html and 'id="catEditMfr"' in html)
    check("every catalogue row draws both buttons", js.count("catActions(") >= 5,
          js.count("catActions("))
    check("EDIT sits beside DEL, not instead of it",
          "editCatalogItem(" in js and "delCatalogItem(" in js)
    check("the toast reports the records it moved", "records updated" in js
          or "record${" in js)
finally:
    c = A.conn(); cur = c.cursor()
    cur.execute("DELETE FROM Assets WHERE _id=%s", [AID])
    cur.execute("DELETE FROM Contracts WHERE name=%s", ["Contract " + TAG])
    for table, names in (("Categories", [CAT_OLD, CAT_NEW]),
                         ("Manufacturers", [MFR_OLD, MFR_NEW, "Other " + TAG]),
                         ("Models", [MOD_OLD, MOD_NEW]),
                         ("ContractTypes", [CT_OLD, CT_NEW])):
        for n in names:
            cur.execute("DELETE FROM `%s` WHERE name=%%s" % table, [n])
    cur.execute("DELETE FROM AuditLog WHERE action='CATALOG_RENAME' AND detail LIKE %s",
                ["%" + TAG + "%"])
    c.commit(); c.close()
    print()
    print("(test catalogue entries, asset and contract removed)")

print()
if fails:
    print("FAILED (%d): %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("ALL PASSED")
