"""An Arabic name survives the trip into the signed-acknowledgement PDF.

Someone signed for an asset, typed their name in Arabic, and the emailed PDF
showed a row of identical boxes. Two independent causes, and either one alone
still ruins the name:

  * reportlab's built-in Helvetica is a Latin-1 font. It has no Arabic glyph
    to draw, so it draws .notdef -- the box.
  * a PDF has no text engine. It stores glyphs at coordinates in the order
    they were written, and no reader reshapes or reorders them. Arabic
    letters change form according to their neighbours and run right to left,
    so that has to happen before anything is drawn.

So: a bundled font that has the glyphs, and shaping + bidi on the way in.

The check that matters is the round trip -- pull the text back out of the
finished PDF and see whether it is still the name that was typed. Reading the
code cannot tell you that, and neither can looking at one rendering.
"""
import io
import os
import re
import sys
import unicodedata

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
import app as A

fails = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (("   " + str(detail)) if detail else ""))
    if not cond:
        fails.append(name)


# written as escapes so this file stays readable in any editor and on any
# console -- cp1252 cannot print the literals
NAME = u"محمد أحمد"      # Muhammad Ahmad
SALAAM = u"سلام"                             # has a lam-alef
HEBREW = u"דוד"                                   # David

print("1. The font is bundled and registered")
for f in ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf", "LICENSE.txt"):
    p = os.path.join(ROOT, "fonts", f)
    check("  fonts/%s ships with the app" % f, os.path.exists(p),
          "%d bytes" % os.path.getsize(p) if os.path.exists(p) else "missing")
A._register_pdf_fonts()
check("  the document font is the Unicode one", A.PDF_FONT == "DejaVuSans", A.PDF_FONT)
check("  and so is its bold face", A.PDF_FONT_BOLD == "DejaVuSans-Bold", A.PDF_FONT_BOLD)
# the fonts are the reason this works at all; a stray .dockerignore line or a
# build that skips them would put the boxes straight back
di = io.open(os.path.join(ROOT, ".dockerignore"), encoding="utf-8-sig").read()
check("  nothing in .dockerignore excludes them",
      not any(l.strip().rstrip("/") in ("fonts", "*.ttf") for l in di.splitlines()))
# core.autocrlf is on for this repo: without an explicit rule git may decide
# a font is text and "fix" its line endings, which corrupts it -- and the
# symptom of a corrupt font is the row of boxes this all exists to remove
ga = io.open(os.path.join(ROOT, ".gitattributes"), encoding="utf-8-sig").read()
check("  git is told they are binary",
      re.search(r"^\*\.ttf\s+binary", ga, re.M) is not None)

print()
print("2. Right-to-left text is recognised, and nothing else is disturbed")
check("  Arabic is detected", A._has_rtl(NAME))
check("  Hebrew is detected", A._has_rtl(HEBREW))
check("  plain English is not", not A._has_rtl("Dell Latitude 5420"))
check("  nor is an asset tag", not A._has_rtl("IT-1042"))
for latin in ("", "IT-1042", "Dell Latitude 5420", u"AED 3,200.00", u"café"):
    check("  %-20r passes through untouched" % latin, A._pdf_text(latin) == latin)
check("  None becomes an empty string, not the word None", A._pdf_text(None) == "")

print()
print("3. Arabic is reshaped and reordered")
out = A._pdf_text(NAME)
forms = [c for c in out if 0xFE70 <= ord(c) <= 0xFEFF]
check("  letters are swapped for their contextual forms", len(forms) >= 8,
      "%d of %d chars" % (len(forms), len(out)))
check("  nothing is lost", len(out) == len(NAME), "%d -> %d" % (len(NAME), len(out)))
# undo both steps: reverse the visual order, then map the presentation forms
# back to the base letters they decompose to
check("  and it is the same name once the display order is undone",
      unicodedata.normalize("NFKC", out[::-1]) == NAME,
      repr(unicodedata.normalize("NFKC", out[::-1])))
# the first letter of the word must end up on the RIGHT, which is the last
# position written -- get this backwards and the name reads inside out
check("  the first letter typed is drawn last", out[-1] != NAME[-1])
lig = A._pdf_text(SALAAM)
check("  lam-alef becomes one ligature glyph",
      any(0xFEF5 <= ord(c) <= 0xFEFC for c in lig),
      " ".join("%04X" % ord(c) for c in lig))
check("  which is why it comes out one character shorter",
      len(lig) == len(SALAAM) - 1, "%d -> %d" % (len(SALAAM), len(lig)))

print()
print("4. The finished PDF still holds the name that was typed")
asset = {"AssetTag": "IT-1042", "Name": "Dell Latitude 5420", "Type": "Laptop",
         "Serial": "SN-ARB-1", "Location": "Head Office", "Status": "Checked-Out",
         "Price": 3200, "WarrantyMonths": 24, "NotesReceived": "2026-09-15",
         "Notes": SALAAM, "_currency": "AED"}
pdf = A._build_signed_asset_pdf(asset, NAME, None)
check("  a PDF is produced", pdf[:5] == b"%PDF-" and len(pdf) > 5000, "%d bytes" % len(pdf))

try:
    import pymupdf
except ImportError:
    try:
        import fitz as pymupdf
    except ImportError:
        pymupdf = None

if pymupdf is None:
    print("  (pymupdf not installed -- skipping the read-back)")
else:
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    page = doc[0]
    spans = [s for b in page.get_text("dict")["blocks"]
             for l in b.get("lines", []) for s in l["spans"]]
    check("  every span is set in the bundled font",
          spans and all("DejaVu" in s["font"] for s in spans),
          sorted({s["font"] for s in spans if "DejaVu" not in s["font"]}))
    text = page.get_text()
    check("  no unmappable character reached the page", "�" not in text)
    # mupdf puts extracted right-to-left text back in logical order, so the
    # only step left to undo is the presentation forms
    got = set()
    for line in text.splitlines():
        arabic = "".join(c for c in line if ord(c) >= 0x0600 or c == " ")
        arabic = unicodedata.normalize("NFKC", arabic).strip()
        if arabic:
            got.add(arabic)
    check("  the signer's name is readable and correct", NAME in got, sorted(got))
    check("  so is an Arabic note", SALAAM in got, sorted(got))
    check("  the English fields are untouched",
          "Dell Latitude 5420" in text and "IT-1042" in text)
    check("  the warranty still carries its unit", "24 months" in text)

print()
print("5. A deployment without the shaping libraries degrades, it does not break")
# the two libraries are in requirements.txt, but an older container or a
# source checkout that skipped pip install must still issue the PDF
saved = {m: sys.modules.get(m) for m in ("arabic_reshaper", "bidi", "bidi.algorithm")}
try:
    for m in saved:
        sys.modules[m] = None       # makes `import m` raise ImportError
    plain = A._pdf_text(NAME)
    check("  the name is returned as typed, not mangled", plain == NAME, repr(plain))
    check("  Latin text is still fine", A._pdf_text("IT-1042") == "IT-1042")
    pdf2 = A._build_signed_asset_pdf(asset, NAME, None)
    check("  and a PDF is still produced", pdf2[:5] == b"%PDF-", "%d bytes" % len(pdf2))
finally:
    for m, v in saved.items():
        if v is None:
            sys.modules.pop(m, None)
        else:
            sys.modules[m] = v
check("  shaping works again afterwards", A._pdf_text(NAME) != NAME)

print()
print("6. The dependencies are declared")
req = io.open(os.path.join(ROOT, "requirements.txt"), encoding="utf-8-sig").read()
check("  arabic-reshaper is required", re.search(r"^arabic-reshaper", req, re.M) is not None)
check("  python-bidi is required", re.search(r"^python-bidi", req, re.M) is not None)
# 0.5+ is a Rust extension and the image has no Rust toolchain: an
# architecture without a prebuilt wheel would fail the docker build
check("  python-bidi is pinned to a pure-Python release",
      re.search(r"^python-bidi==0\.4\.\d", req, re.M) is not None,
      re.search(r"^python-bidi.*", req, re.M).group(0))

print()
print("7. A brand name with an ampersand no longer costs the whole PDF")
# Paragraph parses its text as markup, so & and < used to raise
orig = A.brand_name
try:
    A.brand_name = lambda: "Smith & Jones <IT>"
    pdf3 = A._build_signed_asset_pdf(asset, NAME, None)
    check("  it builds", pdf3[:5] == b"%PDF-", "%d bytes" % len(pdf3))
    if pymupdf is not None:
        t3 = pymupdf.open(stream=pdf3, filetype="pdf")[0].get_text()
        check("  and the name reads correctly", "Smith & Jones <IT>" in t3)
except Exception as e:
    check("  it builds", False, "%s: %s" % (type(e).__name__, e))
finally:
    A.brand_name = orig

print()
print("8. The database is created able to hold the name in the first place")
# MariaDB still defaults to latin1 and MARIADB_DATABASE creates the database
# with the server default, so on a fresh install the name could be reduced to
# question marks on the way in -- a loss no amount of PDF work can undo.
compose = io.open(os.path.join(ROOT, "docker-compose.yml"), encoding="utf-8-sig").read()
inst = io.open(os.path.join(ROOT, "install.sh"), encoding="utf-8-sig").read()
check("  compose starts the server as utf8mb4",
      "--character-set-server=utf8mb4" in compose)
check("  with a utf8mb4 collation", "--collation-server=utf8mb4" in compose)
check("  and so does the installer", "--character-set-server=utf8mb4" in inst)
# the connection has to agree, or the client mangles it instead
check("  every connection asks for utf8mb4",
      io.open(os.path.join(ROOT, "app.py"), encoding="utf-8-sig").read().count('charset="utf8mb4"') >= 3)

print()
if fails:
    print("FAILED (%d): %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("ALL PASSED")
