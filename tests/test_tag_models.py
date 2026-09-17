"""Two shapes of asset tag, because they answer different questions.

"Detailed" is the tag this app has always printed: brand, asset ID, name, the
fields chosen in Settings, and the DO NOT REMOVE notice. It is for an IT team
reading a label off a shelf.

"Plate" is the engraved-plate convention every asset register in the world
uses -- the code on the left, and the owner's mark, one caption and one big
number on the right. Nothing else. It is for identifying a thing across a
room. The four captions offered (Asset No., Council Asset, Product ID Code,
Tracked Asset) are what the plates in circulation actually say; the caption is
free text because the fifth organisation will call it something else again.

The two are checked against each other here, because the easy way to get this
wrong is to let the plate quietly inherit a piece of the detailed tag -- a
border, a field row, the notice strip -- and only find out on a printer.
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


def read(name):
    return io.open(os.path.join(ROOT, name), encoding="utf-8-sig").read()


A.app.config["TESTING"] = True
cl = A.app.test_client()
with cl.session_transaction() as sess:
    sess["user"] = "admin"
    sess["role"] = "admin"

AID = "TM-" + uuid.uuid4().hex[:8]
TAG = "45464544"
NAME = "Boardroom projector"
SERIAL = "SN-TM-1"

c = A.conn(); cur = c.cursor()
cur.execute("SELECT label_model, label_caption, label_size, label_color, label_logo_size, "
            "label_show_name, label_show_contact, label_show_asset FROM Settings WHERE id=1")
before = cur.fetchone() or {}
cur.execute("INSERT INTO Assets (_id, AssetTag, Name, Type, Serial, Status, Location) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (AID, TAG, NAME, "Projector", SERIAL, "Available", "Head Office"))
c.commit(); c.close()
CODE = A._asset_public_code(AID)


def label(model=None, caption=None, size=None, color=None):
    body = {}
    if color is not None:
        body["label_color"] = color
    if model is not None:
        body["label_model"] = model
    if caption is not None:
        body["label_caption"] = caption
    if size is not None:
        body["label_size"] = size
    if body:
        r = cl.put("/api/settings", json=body)
        assert r.status_code == 200, r.status_code
    return cl.get("/label/" + AID).get_data(as_text=True)


try:
    print("1. The model is a setting, and it defaults to what was there before")
    s = cl.get("/api/settings").get_json()
    check("the page is told the model", "label_model" in s and "label_caption" in s)
    check("five models exist",
          A.LABEL_MODELS == ("detail", "plate", "banner", "sidebar", "edge"), A.LABEL_MODELS)
    check("the four captions are offered",
          set(A.LABEL_CAPTION_PRESETS) ==
          {"Asset No.", "Council Asset", "Product ID Code", "Tracked Asset"},
          A.LABEL_CAPTION_PRESETS)
    # an install that never opens the setting must keep the tag it has
    cl.put("/api/settings", json={"label_model": "nonsense"})
    check("an unknown model falls back to detailed",
          cl.get("/api/settings").get_json()["label_model"] == "detail")

    print()
    print("2. Detailed prints what it always did")
    html = label("detail", size="50.8x25.4")
    check("  the brand header is there", "class=brand" in html)
    check("  the chosen fields print", "class=kv" in html)
    check("  the notice strip is there", "class=norem" in html and "Do Not Remove" in html)
    check("  and it is a bordered box", "class=box" in html and "border:1px solid" in html)
    check("  no plate markup leaked in", 'class="tag plate"' not in html)

    print()
    print("3. Plate prints a plate")
    # with the optional lines off, so this measures the model and not them
    cl.put("/api/settings", json={"label_show_name": 0, "label_show_contact": 0,
                                  "label_show_asset": 0, "label_logo_size": "md"})
    html = label("plate", "Asset No.")
    check("  the plate layout is used", 'class="tag plate"' in html)
    check("  the code is a square column", re.search(r"\.pqr\{[^}]*width:[\d.]+mm", html) is not None)
    check("  the caption prints", ">Asset No.<" in html)
    check("  the asset number is the headline", re.search(r"class=pid[^>]*>%s<" % TAG, html) is not None)
    # everything the detailed tag carries and a plate does not
    for gone, why in (("class=kv", "a field row"), ("class=norem", "the notice"),
                      ("class=brand", "the brand strip"), ("class=stack", "the text column")):
        check("  no %s on a plate" % why, gone not in html)
    check("  the asset name is not on it", NAME not in html.split("<title>")[1].split("</title>")[1])
    check("  nor the serial", SERIAL not in html)
    # the photographed plates are cut metal; a printed rule around the edge
    # only makes the alignment look wrong
    check("  and no border is drawn", "border:1px solid #222" not in html)

    print()
    print("4. Every one of the four captions prints as asked")
    for cap in A.LABEL_CAPTION_PRESETS:
        html = label("plate", cap)
        m = re.search(r"class=pcap>([^<]*)<", html)
        check("  %-16s prints" % cap, bool(m) and m.group(1) == cap, m.group(1) if m else "none")
    # free text, because the next organisation calls it something else
    html = label("plate", "Equipment Ref")
    check("  a caption of their own works too", ">Equipment Ref<" in html)
    long_cap = "X" * 80
    cl.put("/api/settings", json={"label_caption": long_cap})
    stored = cl.get("/api/settings").get_json()["label_caption"]
    check("  and an absurd one is capped, not rejected", len(stored) <= 40, len(stored))

    print()
    print("5. The QR is the same address either way")
    for model in ("detail", "plate"):
        html = label(model, "Asset No.")
        m = re.search(r"text:'([^']+)'", html)
        check("  %-6s encodes the public code" % model,
              bool(m) and ("/p/" + CODE) in m.group(1), m.group(1) if m else "none")
    check("  which means a plate scan reaches the same page",
          cl.get("/p/" + CODE).status_code == 200)

    print()
    print("6. A sheet of plates is the same tag, many times")
    sheet = cl.get("/labels?ids=" + AID).get_data(as_text=True)
    check("  the sheet uses the model too", 'class="tag plate"' in sheet)
    check("  one plate per asset", sheet.count('class="tag plate"') == 1,
          sheet.count('class="tag plate"'))
    check("  and the same code", ("/p/" + CODE) in sheet)

    print()
    print("7. It fits the stock, both sizes")
    for size, want_w, want_h in (("50.8x25.4", 50.8, 25.4), ("50.8x50.8", 50.8, 50.8)):
        html = label("plate", "Asset No.", size=size)
        m = re.search(r"\.tag\{width:([\d.]+)mm;height:([\d.]+)mm", html)
        check("  %s renders at its stock size" % size,
              bool(m) and float(m.group(1)) == want_w and float(m.group(2)) == want_h,
              (m.group(1) + "x" + m.group(2)) if m else "no rule")
        # a number that runs off the plate is not a number
        idm = re.search(r"class=pid style=\"font-size:([\d.]+)mm\"", html)
        check("  %s sizes the number to fit" % size,
              bool(idm) and 1.6 <= float(idm.group(1)) <= 6.4,
              idm.group(1) + "mm" if idm else "none")
    # a long asset tag must shrink rather than overflow
    c2 = A.conn(); cur2 = c2.cursor()
    cur2.execute("UPDATE Assets SET AssetTag=%s WHERE _id=%s", ["IT-2026-CORP-0001234", AID])
    c2.commit(); c2.close()
    html = label("plate", "Asset No.", size="50.8x25.4")
    long_id = re.search(r"class=pid style=\"font-size:([\d.]+)mm\"", html)
    check("  a long asset number is shrunk to fit",
          bool(long_id) and float(long_id.group(1)) < 4.6, long_id.group(1) if long_id else "none")
    check("  and printed whole", "IT-2026-CORP-0001234" in html)
    c2 = A.conn(); cur2 = c2.cursor()
    cur2.execute("UPDATE Assets SET AssetTag=%s WHERE _id=%s", [TAG, AID])
    c2.commit(); c2.close()

    print()
    print("7b. The other three models are different tags, not skins")
    # The complaint that produced them: four plate captions all felt like the
    # same tag, because they were. These put the code, the name, the number
    # and the instruction in different places.
    shapes = {}
    # the owner's name and the contact are opt-in now, and this section is
    # about where each model puts them when they are asked for
    cl.put("/api/settings", json={"label_show_name": 1, "label_show_contact": 1})
    for model in ("plate", "banner", "sidebar", "edge"):
        html = label(model, "Return To Equipment Room", size="50.8x25.4", color="#1b4fd8")
        shapes[model] = html
        check("  %-8s renders as itself" % model, 'class="tag %s"' % model in html)
    check("  no two of them share a layout",
          len({re.search(r'class="tag (\w+)"', h).group(1) for h in shapes.values()}) == 4)

    # banner: a colour band with the owner's name, SCAN ME under the code, and
    # the instruction in the largest type on the tag
    b = shapes["banner"]
    check("  banner has a colour band", re.search(r"\.bhead\{[^}]*background:#1b4fd8", b) is not None)
    check("  with the organisation in it, when asked for",
          ">" + A.brand_name() + "<" in b)
    check("  SCAN ME under the code", "SCAN ME" in b)
    check("  and the instruction spelled out", "PLEASE DO NOT REMOVE TAG" in b)
    check("  no number on it -- it is a message tag", "class=pid" not in b)

    # sidebar: owner block on a colour panel, code and number on white, and a
    # colour tab at the far edge so the tag reads end-on in a drawer
    s = shapes["sidebar"]
    check("  panel is the colour", re.search(r"\.sleft\{[^}]*background:#1b4fd8", s) is not None)
    check("  it carries the contact details", A.brand_name() in s)
    check("  and there is an edge tab", "class=stab" in s
          and re.search(r"\.stab\{[^}]*background:#1b4fd8", s) is not None)

    # edge: text and number turned on their side, for something narrow
    e = shapes["edge"]
    check("  spine text is rotated", "writing-mode:vertical-rl" in e)
    check("  so is the number", e.count("writing-mode:vertical-rl") >= 2)
    check("  and the border is the colour",
          re.search(r"\.tag\{[^}]*solid #1b4fd8", e) is not None)

    print()
    print("7c. Text on the colour flips so it can be read")
    # a white band with white text on it is a blank tag
    check("  white ink on a dark band",
          'color:#ffffff' in label("banner", "x", color="#000080"))
    check("  black ink on a light one",
          'color:#111111' in label("banner", "x", color="#ffe600"))
    check("  a junk colour falls back to black",
          re.search(r"\.bhead\{[^}]*background:#000000",
                    label("banner", "x", color="not-a-colour")) is not None)
    check("  and the stored value is the sanitised one",
          cl.get("/api/settings").get_json()["label_color"] == "#000000")

    print()
    print("7d. The optional lines, on every model")
    # Asked for as "add some details like company name" -- so they are the
    # same three switches whichever model is printing, rather than a different
    # set of options per tag.
    # The schema's own defaults, not this install's current values: what
    # matters is that a fresh install prints the tag it printed yesterday.
    c0 = A.conn(); cur0 = c0.cursor()
    cur0.execute("SHOW COLUMNS FROM Settings")
    defaults = {r["Field"]: r["Default"] for r in cur0.fetchall()}
    c0.close()
    for k in ("label_show_name", "label_show_contact", "label_show_asset"):
        check("  %s defaults to off" % k, str(defaults.get(k) or "0") in ("0", "None"),
              defaults.get(k))
    check("  and the logo size defaults to md", (defaults.get("label_logo_size") or "md") == "md",
          defaults.get("label_logo_size"))

    c3 = A.conn(); cur3 = c3.cursor()
    cur3.execute("SELECT company_phone FROM Settings WHERE id=1")
    _phone_before = (cur3.fetchone() or {}).get("company_phone") or ""
    cur3.execute("UPDATE Settings SET company_phone=%s WHERE id=1", ["+971 4 555 0000"])
    c3.commit(); c3.close()
    try:
        BRAND = A.brand_name()
        for model in A.LABEL_MODELS:
            cl.put("/api/settings", json={"label_model": model, "label_show_name": 1,
                                          "label_show_contact": 1, "label_show_asset": 1})
            body = cl.get("/label/" + AID).get_data(as_text=True)
            body = body[body.index("<body"):]
            check("  %-8s prints the company name" % model, BRAND in body)
            check("  %-8s prints the contact number" % model, "+971 4 555 0000" in body)
            check("  %-8s prints the asset name" % model, NAME in body)
        # and off means off, on every one of them
        for model in A.LABEL_MODELS:
            cl.put("/api/settings", json={"label_model": model, "label_show_name": 0,
                                          "label_show_contact": 0, "label_show_asset": 0})
            body = cl.get("/label/" + AID).get_data(as_text=True)
            body = body[body.index("<body"):]
            check("  %-8s drops the contact when unticked" % model,
                  "+971 4 555 0000" not in body)

        print()
        print("7e. Logo size, four steps, capped by the tag")
        for model, rule in (("detail", r"\.logo\{height:([\d.]+)mm"),
                            ("plate", r"\.plogo\{height:([\d.]+)mm"),
                            ("sidebar", r"\.slogo\{height:([\d.]+)mm"),
                            ("edge", r"\.elogo\{height:([\d.]+)mm")):
            sizes = []
            for step in ("sm", "md", "lg", "xl"):
                cl.put("/api/settings", json={"label_model": model, "label_logo_size": step})
                m = re.search(rule, cl.get("/label/" + AID).get_data(as_text=True))
                sizes.append(float(m.group(1)) if m else -1.0)
            check("  %-8s grows with the setting" % model,
                  sizes == sorted(sizes) and sizes[0] > 0 and sizes[-1] > sizes[0], sizes)
            check("  %-8s stays inside the tag" % model, max(sizes) <= 25.4 * 0.45, max(sizes))
        check("an unknown step falls back to the default",
              cl.put("/api/settings", json={"label_logo_size": "enormous"}).status_code == 200
              and cl.get("/api/settings").get_json()["label_logo_size"] == "md")

        print()
        print("7f. A partial save does not wipe them")
        # This one bit: every column the save writes has to be in the row it
        # reads first, or a branding-only save stores the default over it.
        cl.put("/api/settings", json={"label_model": "plate", "label_show_name": 1,
                                      "label_show_contact": 1, "label_show_asset": 1,
                                      "label_logo_size": "lg"})
        cl.put("/api/settings", json={"label_caption": "Asset No."})
        after = cl.get("/api/settings").get_json()
        for k, want in (("label_show_name", 1), ("label_show_contact", 1),
                        ("label_show_asset", 1), ("label_logo_size", "lg")):
            check("  %s survived a caption-only save" % k,
                  (int(after[k]) if k != "label_logo_size" else after[k]) == want, after[k])
    finally:
        c3 = A.conn(); cur3 = c3.cursor()
        cur3.execute("UPDATE Settings SET company_phone=%s WHERE id=1", [_phone_before])
        c3.commit(); c3.close()

    print()
    print("7g. The code box rule does not reach the logo")
    # As ".tag img" it did, overriding the logo's height with auto -- so a
    # logo printed at whatever size the uploaded file happened to be.
    html = label("plate", "Asset No.")
    check("  the rule is scoped to the code boxes",
          ".pqr canvas,.pqr img" in html and ".tag canvas,.tag img" not in html)

    print()
    print("8. The picker is wired to it")
    html_idx = read("index.html")
    js = read("app.js")
    css = read("style.css")
    check("there is a model grid", 'id="tagModelGrid"' in html_idx)
    for model in A.LABEL_MODELS:
        check("  %-8s is offered as a card" % model, 'data-model="%s"' % model in html_idx)
    check("each card carries the text that model is usually printed with",
          'data-caption="Return To Equipment Room"' in html_idx)
    check("the colour is a colour input", 'type="color" id="label_color"' in html_idx)
    check("the logo size reads like the QR size", 'id="label_logo_size"' in html_idx
          and html_idx.index('id="qr_size"') < html_idx.index('id="label_logo_size"'))
    for tid in ("label_show_name", "label_show_contact", "label_show_asset"):
        check("  %s has a switch" % tid, 'id="%s"' % tid in html_idx and tid in js)
    check("and it is only shown for the models that use it",
          "TAG_COLOURED" in js and "labelColorWrap" in js)
    check("each card shows a drawing of its tag",
          ".tm-prev{" in css and 'class="tm-q"' in html_idx)
    check("the caption is editable", 'id="label_caption"' in html_idx)
    check("the save sends both", "label_model: TAG_MODEL" in js and "label_caption:" in js)
    # field checkboxes do nothing on a plate, so they are put away rather
    # than left sitting there looking connected
    check("the field list hides for a plate",
          "labelFieldsPanel" in js and 'id="labelFieldsPanel"' in html_idx)
finally:
    c = A.conn(); cur = c.cursor()
    cur.execute("DELETE FROM Assets WHERE _id=%s", [AID])
    cur.execute("UPDATE Settings SET label_model=%s, label_caption=%s, label_size=%s, "
                "label_color=%s, label_logo_size=%s, label_show_name=%s, "
                "label_show_contact=%s, label_show_asset=%s WHERE id=1",
                (before.get("label_model") or "detail",
                 before.get("label_caption") or "Asset No.",
                 before.get("label_size") or "50.8x25.4",
                 before.get("label_color") or "#000000",
                 before.get("label_logo_size") or "md",
                 int(before.get("label_show_name") or 0),
                 int(before.get("label_show_contact") or 0),
                 int(before.get("label_show_asset") or 0)))
    c.commit(); c.close()
    print()
    print("(test asset removed, label settings restored)")

print()
if fails:
    print("FAILED (%d): %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("ALL PASSED")
