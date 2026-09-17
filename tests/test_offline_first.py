"""Every screen in the app paints from the cache before it asks the server.

The app cached plenty and showed almost none of it. A list kept its rows only
as a fallback for a failed fetch, and a form fetched five reference lists and
the record over the network before drawing a single field -- so opening an
asset you had opened minutes ago still meant watching a spinner, with the
asset sitting on the phone the whole time. The cache was only ever consulted
once something had already gone wrong.

What this checks is the order, per screen: something is read out of
OfflineCache before the first ApiClient call in that screen's load path. It
is a crude test of a simple property, and the property is the whole
difference between an app that feels instant and one that does not.

It also holds the reference lists (categories, manufacturers, models,
locations, departments, contract types) in the cache and in the start-up
warm-up, because a form cannot draw itself from the cache without them.
"""
import io
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
UI = os.path.join(ROOT, "android-app", "app", "src", "main", "java", "com", "itguy",
                  "assetmanager", "ui")
DATA = os.path.join(ROOT, "android-app", "app", "src", "main", "java", "com", "itguy",
                    "assetmanager", "data")

fails = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (("   " + str(detail)) if detail else ""))
    if not cond:
        fails.append(name)


def read(path):
    return io.open(path, encoding="utf-8-sig").read()


def load_path(text, start_marker, end_marker):
    """The body of the function that fetches a screen's data."""
    i = text.index(start_marker)
    j = text.index(end_marker, i + len(start_marker))
    return text[i:j]


print("\nthe cache is read before the network, screen by screen")
SCREENS = (
    ("asset form", "assets/AssetEditFragment.kt",
     "private fun loadReferenceDataAndAsset() {", "private fun bindAll("),
    ("asset list", "assets/AssetsListFragment.kt",
     "private fun load(query: String) {", "private fun prepaintFromCache("),
    ("contract form", "contracts/ContractEditFragment.kt",
     "private fun load() {", "private fun bindAll("),
    ("contract list", "contracts/ContractsListFragment.kt",
     "private fun load() {", "private fun showFromCache("),
    ("ticket", "tickets/TicketDetailFragment.kt",
     "private fun load() {", "private fun render("),
    ("ticket list", "tickets/TicketsListFragment.kt",
     "private fun load() {", "private fun showFromCache("),
    ("dashboard", "dashboard/DashboardFragment.kt",
     "override fun refresh() {", "private fun renderBars("),
    ("directory", "employees/DirectoryFragment.kt",
     "private fun load() {", "private fun renderEmployees("),
)

for label, rel, start, end in SCREENS:
    try:
        body = load_path(read(os.path.join(UI, rel)), start, end)
    except ValueError as e:
        check("  %-14s load path found" % label, False, e)
        continue
    # a direct read, or a call to the screen's own prepaint helper -- which is
    # itself asserted to read the cache, further down
    cache_at = min([body.find(m) for m in ("OfflineCache.load", "cache.load", "prepaint")
                    if body.find(m) >= 0] or [-1])
    api_at = body.find("ApiClient.api()")
    check("  %-14s reads the cache first" % label,
          cache_at >= 0 and (api_at < 0 or cache_at < api_at),
          "cache@%s api@%s" % (cache_at, api_at))

print("\nand a prepaint helper really is a cache read")
for label, rel in (("asset list", "assets/AssetsListFragment.kt"),
                   ("dashboard", "dashboard/DashboardFragment.kt")):
    src = read(os.path.join(UI, rel))
    for marker in ("private fun prepaintFromCache(", "private fun prepaintLists("):
        if marker in src:
            helper = src[src.index(marker):]
            helper = helper[:helper.index("\n    private fun ", 10)]
            check("  %-14s %s" % (label, marker.split("fun ")[1].rstrip("(")),
                  "OfflineCache.load" in helper)

print("\nthe reference lists a form fills its dropdowns from")
cache = read(os.path.join(DATA, "OfflineCache.kt"))
for name in ("Categories", "Manufacturers", "Models", "Locations", "Departments",
             "ContractTypes"):
    check("  %-14s is cached" % name,
          ("fun save%s(" % name) in cache and ("fun load%s(" % name) in cache)
check("  a ticket's replies are cached per ticket",
      "fun saveTicketDetail(" in cache and "fun loadTicketDetail(" in cache,
      "the list cache holds the ticket but not the conversation")

print("\nand they are warmed at start-up, not on first use")
boot = read(os.path.join(UI, "BootOverlay.kt"))
for call in ("saveCategories", "saveManufacturers", "saveModels", "saveLocations",
             "saveDepartments", "saveContractTypes"):
    check("  %-18s warmed" % call, call in boot)

print("\nrefreshing must not fight the person using the form")
form = read(os.path.join(UI, "assets/AssetEditFragment.kt"))
check("the form only repaints when the record actually changed",
      "fresh != current" in form,
      "a redraw under someone's fingers loses whatever they were typing")

print()
if fails:
    print("FAILED (%d): %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("ALL PASSED")
