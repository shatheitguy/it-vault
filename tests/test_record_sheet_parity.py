"""The asset sheet prints the same from a phone as from a desk.

There are two implementations of it and there has to be: the browser builds
the sheet from the asset the page already holds, and the phone builds it from
the asset it already holds, which is what lets it print in a store room with
no signal. Two implementations drift -- the phone's started life without the
letterhead and without the signature block, which is exactly the complaint
that produced this file.

So this pins the parts that make them the same document: the letterhead
handling (same clearance, same full-page backdrop, same suppressed header),
the ID bar, the field table, and the signature block. It deliberately does
not compare them character by character -- one is JavaScript building a
document it will print immediately, the other is Kotlin building a string for
a WebView, and they are allowed to differ in how they get there.
"""
import io
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
KT = os.path.join(ROOT, "android-app", "app", "src", "main", "java", "com", "itguy",
                  "assetmanager", "ui", "assets", "RecordViewActivity.kt")

fails = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (("   " + str(detail)) if detail else ""))
    if not cond:
        fails.append(name)


web = io.open(os.path.join(ROOT, "app.js"), encoding="utf-8-sig").read()
kt = io.open(KT, encoding="utf-8-sig").read()

# the web's sheet is one function; the phone's is one method
web_sheet = web[web.index("async function printAsset(id)"):]
web_sheet = web_sheet[:web_sheet.index("\n}\n")]
kt_sheet = kt[kt.index("private fun buildHtml("):]
kt_sheet = kt_sheet[:kt_sheet.index("private fun esc(")]
# Kotlin escapes the quotes inside its string literals; compare the markup,
# not the escaping
kt_sheet = kt_sheet.replace('\\"', '"')

print("\nthe letterhead")
m_web = re.search(r"LETTERHEAD_CLEARANCE_MM\s*=\s*(\d+)", web)
m_kt = re.search(r"LETTERHEAD_CLEARANCE_MM\s*=\s*(\d+)", kt)
check("both leave the same gap at the top of the page",
      m_web and m_kt and m_web.group(1) == m_kt.group(1),
      "web=%s phone=%s" % (m_web and m_web.group(1), m_kt and m_kt.group(1)))

for label, text, whole in (("web", web_sheet, web), ("phone", kt_sheet, kt)):
    check("  %-5s draws the letterhead full page" % label,
          "210mm" in text and "297mm" in text and "object-fit:fill" in text)
    check("  %-5s drops its own header when there is a letterhead" % label,
          "letterhead.png" in whole and "/logo.png" in text)
    check("  %-5s prints edge to edge on letterhead, margins without" % label,
          "14mm" in text and re.search(r"@page\{size:A4;margin:", text) is not None)

# The browser re-fetches what it links while printing. Android's print
# pipeline renders the page it was handed, so the phone has to have the image
# in the document already -- and a fixed backdrop does not survive that
# pipeline either. Both of those were why the letterhead came out missing.
check("the phone inlines the letterhead rather than linking it",
      "data:image/png;base64," in kt and "letterheadDataUri" in kt)
check("the phone positions the backdrop absolutely, not fixed",
      ".lh{position:absolute" in kt_sheet)
check("the phone decides by what came back, not by a server flag",
      "inJustDecodeBounds" in kt and "outWidth < 200" in kt,
      "an install with no letterhead gets a 1x1 PNG, not a 404, so the bytes "
      "arriving prove nothing -- and an install too old to report "
      "has_letterhead must still print its letterhead")

print("\nthe record itself")
for label, text in (("web", web_sheet), ("phone", kt_sheet)):
    check("  %-5s prints the ID bar" % label,
          'class="idbar"' in text and 'class="tag"' in text and 'class="nm"' in text)
    check("  %-5s prints the field table" % label,
          'class="k"' in text and 'class="v"' in text)
    check("  %-5s spells the warranty out in months" % label, "months" in text)

print("\nthe signature")
for label, text in (("web", web_sheet), ("phone", kt_sheet)):
    check("  %-5s has the acknowledgement block" % label,
          "SIGNATURE / ACKNOWLEDGEMENT" in text)
    check("  %-5s prints the captured signature at the same size" % label,
          "max-width:340px" in text and "max-height:160px" in text)
    check("  %-5s says so when nothing has been signed" % label,
          "Not signed yet" in text)

print("\nwhat the phone adds, because it can print with no network")
check("a sheet built from the cache leaves a line to sign",
      "sig-line" in kt_sheet,
      "the cached record carries no signature, so it cannot claim 'not signed yet'")
check("the signature only prints when it is really a data: image",
      'startsWith("data:image")' in kt_sheet)

print("\nthe fields the web prints are all on the phone's sheet too")
for field in ("Price", "Received by", "Notes on receipt", "Employee name",
              "Department", "Designation", "Email"):
    check("  %-18s" % field, '"%s"' % field in kt_sheet)

print()
if fails:
    print("FAILED (%d): %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("ALL PASSED")
