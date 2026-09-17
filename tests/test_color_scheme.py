"""Light or dark comes from the device. Everything else still comes from Settings.

Whether an interface is light or dark is not really an admin's decision. The
person holding the phone already answered it once, for every app they own,
and expects this one to agree. What the admin picks is the brand: the accent,
the radius, the typeface, the hue of the ground.

The whole palette is computed from two values -- the page ground and the card
surface -- so following the device means swinging exactly those two and
letting text, muted text, lines and button ink derive from them as they
always did. A background already on the right side of the line is left alone,
which is why a dark install in dark mode is unchanged.

There are five copies of that engine (the app, the login page, the public
scan/sign pages, the portal and the monitor wall) because these pages are
served standalone and cannot share a module. Five copies that drift are the
real risk here, so every one of them is checked.

The arithmetic is executed, not pattern-matched: a yellow brand colour on a
near-white surface is the case that decides whether light mode is usable, and
no amount of reading the source tells you the contrast ratio.
"""
import io
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

fails = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (("   " + str(detail)) if detail else ""))
    if not cond:
        fails.append(name)


def read(name):
    return io.open(os.path.join(ROOT, name), encoding="utf-8-sig").read()


ENGINES = {
    "app.js": read("app.js"),
    "login.html": read("login.html"),
    "app.py (scan + sign pages)": read("app.py"),
    "portal.html": read("portal.html"),
    "monitor.html": read("monitor.html"),
}
css = read("style.css")

print("1. Every page that themes itself asks the device")
for name, src in ENGINES.items():
    check("  %-28s reads prefers-color-scheme" % name,
          "prefers-color-scheme: light" in src and "function prefersLight(" in src)
    check("  %-28s swings the ground and the surface" % name,
          src.count("toScheme(") >= 3, src.count("toScheme("))

print()
print("2. The accent is not quietly ruined to make light mode work")
for name, src in ENGINES.items():
    # the old guard mixed the accent INTO the surface it had to stand out
    # from, which on white turns a yellow into a paler yellow
    check("  %-28s no longer mixes toward the surface" % name,
          "v*0.65 + s[i]*0.35" not in src and "v*0.65+s[i]*0.35" not in src)
    check("  %-28s moves it away instead" % name,
          "isLightHex(surface)?'#000000':'#ffffff'" in src.replace(" ", ""))

print()
print("3. A scheme change mid-session is picked up")
check("the app re-applies", "addEventListener('change', _onScheme)" in ENGINES["app.js"])
check("and so does a scanned tag",
      "applySignTheme._bound" in ENGINES["app.py (scan + sign pages)"])

print()
print("4. Nothing paints dark first on a light device")
check("the stylesheet declares both schemes", "color-scheme:light dark" in css)
check("and carries light first-paint values",
      re.search(r"@media \(prefers-color-scheme: light\)\s*\{\s*:root\{", css) is not None)
for page in ("portal.html", "monitor.html"):
    src = ENGINES[page]
    check("  %s too" % page,
          "color-scheme:light dark" in src
          and "@media (prefers-color-scheme: light)" in src)

print()
print("5. The arithmetic, executed")
node = None
for cand in ("node", "node.exe"):
    try:
        subprocess.check_output([cand, "--version"], stderr=subprocess.STDOUT)
        node = cand
        break
    except Exception:
        pass

if node is None:
    print("  (node not installed -- skipping)")
else:
    appjs = ENGINES["app.js"]
    need = []
    for fn in ("hex6", "hexRgb", "shade", "isLightHex", "contrastRatio",
               "prefersLight", "mixHex", "toScheme", "ensureAccentVisible", "onBg"):
        m = re.search(r"\nfunction %s\(.*?\n\}" % fn, appjs, re.S)
        if not m:
            check("%s is defined" % fn, False)
        else:
            need.append(m.group(0))
    harness = """
var window = { matchMedia: function(){ return {matches:false}; } };
%s
var DARK_BG='#000000', DARK_SURFACE='#000000', YELLOW='#f1ff2e';
var lightBg=toScheme(DARK_BG,true,false), lightSurface=toScheme(DARK_SURFACE,true,true);
console.log(JSON.stringify({
  darkUntouched: [toScheme(DARK_BG,false,false), toScheme(DARK_SURFACE,false,true)],
  lightBg: lightBg,
  lightSurface: lightSurface,
  lightBgIsLight: isLightHex(lightBg),
  lightSurfaceIsLight: isLightHex(lightSurface),
  surfaceAboveGround: contrastRatio(lightSurface,'#000000') > contrastRatio(lightBg,'#000000'),
  textOnLight: onBg(lightBg),
  lightAlreadyLight: toScheme('#f4f6fa',true,false),
  darkFromLight: toScheme('#f4f6fa',false,false),
  darkFromLightIsDark: !isLightHex(toScheme('#f4f6fa',false,false)),
  yellowOnWhiteRaw: contrastRatio(YELLOW,'#ffffff'),
  yellowFixed: ensureAccentVisible(YELLOW, lightSurface),
  yellowFixedContrast: contrastRatio(ensureAccentVisible(YELLOW,lightSurface), lightSurface),
  yellowOnBlackUntouched: ensureAccentVisible(YELLOW,'#000000')
}));
""" % ("\n".join(need),)
    tmp = os.path.join(tempfile.gettempdir(), "itvault_scheme_check.js")
    io.open(tmp, "w", encoding="utf-8").write(harness)
    r = None
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
        # a dark install in dark mode must be exactly what it always was
        check("  dark stays untouched in dark mode",
              r["darkUntouched"] == ["#000000", "#000000"], r["darkUntouched"])
        check("  a black ground becomes light", r["lightBgIsLight"], r["lightBg"])
        check("  and the card surface with it", r["lightSurfaceIsLight"], r["lightSurface"])
        # cards have to read as raised off the page, not merge into it
        check("  the surface is lighter than the ground",
              r["surfaceAboveGround"], "%s vs %s" % (r["lightSurface"], r["lightBg"]))
        check("  text flips to dark ink", r["textOnLight"] == "#16202e", r["textOnLight"])
        check("  a light ground in light mode is left alone",
              r["lightAlreadyLight"] == "#f4f6fa", r["lightAlreadyLight"])
        check("  and is darkened when the device is dark",
              r["darkFromLightIsDark"], r["darkFromLight"])

        # the case that decides whether light mode is usable at all
        check("  yellow on white really is unreadable to begin with",
              r["yellowOnWhiteRaw"] < 2.2, round(r["yellowOnWhiteRaw"], 2))
        check("  so it is darkened until it can be read",
              r["yellowFixedContrast"] >= 2.2, round(r["yellowFixedContrast"], 2))
        # still their colour: red and green well above blue is still a yellow
        fixed = r["yellowFixed"]
        rr, gg, bb = int(fixed[1:3], 16), int(fixed[3:5], 16), int(fixed[5:7], 16)
        check("  and it is still a yellow, not a new colour",
              rr > bb + 40 and gg > bb + 40, fixed)
        check("  on a dark surface it is not touched at all",
              r["yellowOnBlackUntouched"] == "#f1ff2e", r["yellowOnBlackUntouched"])

print()
if fails:
    print("FAILED (%d): %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("ALL PASSED")
