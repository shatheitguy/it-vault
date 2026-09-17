"""The installer's banner animates without leaving frames behind.

This has gone wrong once already. Animating a block of ASCII art the obvious
way means redrawing it -- move the cursor back up over it, paint the next
frame -- and on screen that looks like one banner. In scrollback, and in any
captured install log, it leaves every frame behind: the install output showed
the banner three times.

So the rule is that the animation only ever rewrites a line in place, with a
carriage return, or appends to it. That keeps one line in the terminal's
buffer per line of output, and what survives is the last thing written to it.
This file holds that rule, the guards that keep the animation optional, and
the fact that a piped install still gets plain text.
"""
import io
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

fails = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (("   " + str(detail)) if detail else ""))
    if not cond:
        fails.append(name)


raw = io.open(os.path.join(ROOT, "install.sh"), "rb").read()
sh = raw.decode("utf-8")
banner = sh[sh.index("banner() {"):]
banner = banner[:banner.index("\nwarn()")]
animated = banner[banner.index("_pulse="):]

print("\nline endings")
check("install.sh is LF, as .gitattributes pins it",
      b"\r\n" not in raw,
      "a CRLF shell script does not run at all")

print("\nthe rule: never redraw upwards")
check("the animation moves the cursor up nowhere",
      not re.search(r"\\033\[[0-9]*A", animated),
      "that is what left three banners in the install log")
check("each art frame is a carriage-return rewrite",
      animated.count("\\r\\033[38;5;") >= 1 and "\\r\\033[1;38;5;203m" in animated,
      "a rewrite stays inside one line of the buffer")
check("the rule under the art is appended, not rewritten",
      "printf '\\033[38;5;203m\\342\\224\\200\\033[0m'" in animated,
      "one character at a time, so it sweeps and leaves one line")

print("\nthe animation is a nicety, and stays optional")
for what, needle in (
    ("only on a terminal", "[ -t 1 ]"),
    ("only if the art cannot wrap", '"${_cols:-0}" -ge 62'),
    ("only if sleep takes fractions", "sleep 0.02 2>/dev/null"),
    ("only on a colour terminal", "*256color*"),
):
    check("  %-32s" % what, needle in banner)

print("\npiped, or on a dumb terminal, the text is unchanged")
check("the flat path prints both subtitle lines",
      '"$BANNER_SUB1"' in banner and '"$BANNER_SUB2"' in banner)
check("the subtitles are still assembled from pad + text",
      'BANNER_SUB1="${BANNER_PAD1}${BANNER_TXT1}"' in sh and
      'BANNER_SUB2="${BANNER_PAD2}${BANNER_TXT2}"' in sh,
      "split so the animated path can type them a word at a time")

print("\nthe glitch is the same one the app's start-up screen uses")
check("there is a cyan frame in the ramp",
      re.search(r"_pulse='[^']*\b45\b", animated) is not None,
      "45 is the cyan tear; the rest of the ramp is ember to accent")
check("it settles on the brand accent",
      "203" in animated, "#ff3b30 in 256-colour terms")

print("\nand it does not become a wait")
sleeps = re.findall(r"sleep (0\.\d+)", animated)
worst = len(sleeps) and sum(float(s) for s in sleeps)
check("few enough sleeps that a slow spawn still lands under a second",
      len(sleeps) <= 4,
      "%d sleep calls in the animated path, %ss of requested delay total"
      % (len(sleeps), worst))

print()
if fails:
    print("FAILED (%d): %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("ALL PASSED")
