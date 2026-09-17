"""The Warranty field says what unit it is in.

The column is WarrantyMonths and everything that reads it back -- the table
cell ("24 mo"), the expiry KPI, the printed tag, the scanned tag -- is months.
The form said none of that: a box labelled "Warranty" with a bare number in
it. Twelve what? Someone typing 2 for "two years" gets an asset out of
warranty in two months, and nothing on the page would have told them.

So the label carries the unit, the box is a number box, and a line under it
says what the number works out to -- 18 -> "1 year 6 months" -- plus the day
cover ends, once there is a purchase date to count from.

The month->words arithmetic is executed here, not pattern-matched, because
off-by-one plurals and the 12/24 boundary are exactly where it would be wrong.
"""
import io
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# node runs the real functions lifted out of app.js; the only thing stubbed is
# the handful of elements warrantyHint() reads
HARNESS = """
var FIELDS = {};
var document = { getElementById: function (id) {
  return (id in FIELDS) ? FIELDS[id] : null;
} };
%s
function hint(months, purchase) {
  FIELDS = {
    warrHint: { textContent: '' },
    f_WarrantyMonths: { value: months },
    f_PurchaseDate: { value: purchase }
  };
  warrantyHint();
  return FIELDS.warrHint.textContent;
}
console.log(JSON.stringify({
  words: { 1: monthsInWords(1), 12: monthsInWords(12), 18: monthsInWords(18),
           24: monthsInWords(24), 25: monthsInWords(25), 36: monthsInWords(36) },
  blank: hint('', ''),
  zero: hint('0', ''),
  one: hint('1', ''),
  six: hint('6', ''),
  twelve: hint('12', ''),
  eighteen: hint('18', ''),
  dated: hint('12', '2026-09-15'),
  dated18: hint('18', '2026-09-15'),
  junkdate: hint('24', '15/09/2026'),
  negative: hint('-3', '')
}));
"""

fails = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (("   " + str(detail)) if detail else ""))
    if not cond:
        fails.append(name)


def read(name):
    return io.open(os.path.join(ROOT, name), encoding="utf-8-sig").read()


js = read("app.js")
py = read("app.py")
css = read("style.css")

print("1. The form states the unit")
m = re.search(r"if\(c==='WarrantyMonths'\)return`(.*?)`;", js, re.S)
check("the warranty field has its own branch", bool(m))
field = m.group(1) if m else ""
check("  the label says months", "(in months)" in field, field[:80])
check("  it is a number box, not free text", 'type="number"' in field)
check("  whole months only", 'step="1"' in field and 'min="0"' in field)
check("  the default is shown as the placeholder", 'placeholder="12"' in field)
check("  typing updates the explanation", 'oninput="warrantyHint()"' in field)
check("  and there is somewhere to put it", 'id="warrHint"' in field)
check("  the hint has a style", ".fhint{" in css)

print()
print("2. The explanation is computed, not guessed")
# pull the functions straight out of app.js and run them for real
need = []
for fn in ("monthsInWords", "warrantyEnd", "warrantyHint"):
    mm = re.search(r"\nfunction %s\(.*?\n\}" % fn, js, re.S)
    check("%s is defined" % fn, bool(mm))
    if mm:
        need.append(mm.group(0))

node = None
for cand in ("node", "node.exe"):
    try:
        subprocess.check_output([cand, "--version"], stderr=subprocess.STDOUT)
        node = cand
        break
    except Exception:
        pass

r = None
if node is None:
    print("  (node not installed -- skipping the arithmetic)")
else:
    # warrantyHint talks to the DOM; give it the three elements it looks for
    harness = HARNESS % ("\n".join(need),)
    tmp = os.path.join(tempfile.gettempdir(), "itvault_warranty_check.js")
    io.open(tmp, "w", encoding="utf-8").write(harness)
    try:
        raw = subprocess.check_output([node, tmp], stderr=subprocess.STDOUT)
        r = json.loads(raw.decode("utf-8").strip().splitlines()[-1])
    except subprocess.CalledProcessError as e:
        check("the harness runs", False, e.output.decode("utf-8", "replace")[:300])
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass

if r:
    w = r["words"]
    check("  1 month stays singular", w["1"] == "1 month", w["1"])
    check("  12 is a year", w["12"] == "1 year", w["12"])
    check("  18 is a year and six months", w["18"] == "1 year 6 months", w["18"])
    check("  24 is two years, with no stray months", w["24"] == "2 years", w["24"])
    check("  25 keeps the odd month", w["25"] == "2 years 1 month", w["25"])
    check("  36 is three years", w["36"] == "3 years", w["36"])

    check("  blank explains the default",
          "12 months" in r["blank"] and "1 year" in r["blank"], r["blank"])
    check("  0 is spelled out as no warranty", "no warranty" in r["zero"].lower(), r["zero"])
    # 0 must not become the 12-month default via the ||'12' inside
    # warrantyEnd -- "no warranty, covered until next year" is nonsense
    check("  0 gets no expiry date", "until" not in r["zero"], r["zero"])
    check("  1 reads as one month", r["one"].startswith("1 month"), r["one"])
    check("  under a year, no year translation", "=" not in r["six"], r["six"])
    check("  12 translates to a year", "= 1 year" in r["twelve"], r["twelve"])
    check("  18 translates in full", "= 1 year 6 months" in r["eighteen"], r["eighteen"])
    check("  a purchase date gives an end date", "2027-09-15" in r["dated"], r["dated"])
    check("  and it counts in months, not years", "2028-03-15" in r["dated18"], r["dated18"])
    check("  an unparseable date is skipped, not guessed",
          "until" not in r["junkdate"], r["junkdate"])
    check("  a negative number is refused", "whole number" in r["negative"], r["negative"])

print()
print("3. A purchase date is picked, so the expiry maths has something to parse")
# the server parses PurchaseDate with strptime("%Y-%m-%d") for the "expiring
# in 30 days" count; a free-text box let anything through
m = re.search(r"if\(c==='PurchaseDate'\)return`(.*?)`;", js, re.S)
check("the purchase date has its own branch", bool(m))
pd = m.group(1) if m else ""
check("  a date picker when the value is safe", "type=" in pd and "date" in pd)
check("  guarded by an ISO test", r"\d{4}-\d{2}-\d{2}" in pd, pd[:120])
# an existing "15/09/2026" in a date input renders blank, and the next save
# would write that blank back over a real value
check("  a value it cannot parse stays a text box", "!val" in pd, pd[:120])
check("  changing it refreshes the warranty line", "warrantyHint()" in pd)

print()
print("4. The hint is painted before the user touches anything")
check("openModal calls it once the fields exist",
      re.search(r"\n  warrantyHint\(\);", js) is not None)

print()
print("5. Everything that prints the number prints a unit")
check("the table cell says mo", re.search(r"WarrantyMonths\|\|12\} mo", js) is not None)
check("the asset detail printout says months",
      re.search(r"f==='WarrantyMonths'.*?' months'", js) is not None)
check("the signed PDF says months", '+ " months"' in py and "WarrantyMonths" in py)
# the tag and the scanned page are tight on space -- "mo" there is deliberate
check("the printed tag still abbreviates",
      py.count('str(asset.get("WarrantyMonths") or 12) + " mo"') >= 3)

print()
if fails:
    print("FAILED (%d): %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("ALL PASSED")
