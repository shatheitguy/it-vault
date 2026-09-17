"""What the acknowledgement sheet shows, and the one thing it must not.

This is the page somebody signs to say they have the laptop. It is handed to
them and mailed to their inbox, so it is the one printout that leaves the IT
department -- and what the organisation paid for the thing has no business on
it. The price is still on the asset record, on the internal print, and in
every export; it is off this sheet alone.

Reading the code cannot prove that. A price could reach the page through the
notes, through a field added later, through the currency stamped on something
else. So this builds a real PDF from an asset that has a price, pulls the
text back out of it, and looks for the number.

The rest of the file is the other half of the same question: taking a row out
must not take its neighbours with it, so the fields that have to stay are
listed here too.
"""

import io
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
import app as A

fails = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (("   " + str(detail)) if detail else ""))
    if not cond:
        fails.append(name)


ASSET = {
    "AssetTag": "IT-9042", "Name": "Dell Latitude 5440", "Type": "Laptop",
    "Serial": "7XJ4K93", "Location": "Head Office", "Status": "Checked-Out",
    # a price, deliberately: the point is that it is carried and not printed
    "Price": "4250.00", "_currency": "AED",
    "WarrantyMonths": 36, "NotesReceived": "2026-09-17",
    "Notes": "boxed, charger included", "EmployeeID": "EMP-204",
    "EmployeeName": "A. Fernandes", "Department": "Operations",
    "Designation": "Site Supervisor", "Email": "a.fernandes@example.com",
}

pdf = A._build_signed_asset_pdf(ASSET, "A. Fernandes", None)
check("a PDF is produced", pdf[:5] == b"%PDF-" and len(pdf) > 3000, "%d bytes" % len(pdf))

try:
    import pymupdf
except ImportError:
    try:
        import fitz as pymupdf
    except ImportError:
        pymupdf = None

if pymupdf is None:
    print("\n  (pymupdf not installed -- cannot read the PDF back, so this "
          "file can only check that one was built)")
else:
    text = "\n".join(page.get_text() for page in pymupdf.open(stream=pdf, filetype="pdf"))

    print("\nthe price is not on the signed copy")
    for probe in ("Price", "4250", "4,250", "4250.00", "AED"):
        check("  %-8s does not appear" % probe, probe not in text)

    print("\nand everything else still is")
    for label in ("Asset ID", "Asset Name", "Item Category", "Serial", "Location",
                  "Status", "Warranty", "Signed Date", "Notes", "Signed By"):
        check("  %-13s" % label, label in text)
    for value in ("IT-9042", "Dell Latitude 5440", "7XJ4K93", "36 months",
                  "2026-09-17", "A. Fernandes"):
        check("  %-20s" % value, value in text)

    print("\nthe person it was handed to is still named")
    for label in ("Employee Name", "Department", "Designation", "Email"):
        check("  %-14s" % label, label in text)

    print("\nan asset with no employee still produces a sheet")
    lone = {k: v for k, v in ASSET.items() if k not in
            ("EmployeeID", "EmployeeName", "Department", "Designation", "Email")}
    pdf2 = A._build_signed_asset_pdf(lone, "Store keeper", None)
    t2 = "\n".join(p.get_text() for p in pymupdf.open(stream=pdf2, filetype="pdf"))
    check("  it builds", pdf2[:5] == b"%PDF-")
    check("  with no employee block", "Designation" not in t2)
    check("  and still no price", "4250" not in t2 and "AED" not in t2)

print()
if fails:
    print("FAILED (%d): %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("ALL PASSED")
