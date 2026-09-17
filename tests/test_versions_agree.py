"""Every place that states a version has to state the same one.

They drifted badly once: VERSION said 1.8.0, the Android build said 1.9.0, and
the update manifest installed phones poll said 1.6.2 -- older in name than the
release already shipped, so the in-app updater offered a "new" version that
read as a downgrade. Nothing anywhere failed, because nothing was checking.

Four sources, one number:

  VERSION                          what the web app reports and compares
                                   against GitHub releases on an update check
  android .../build.gradle.kts     versionName, shown in the app
  docs/app/latest.json             versionName + versionCode the in-app
                                   updater polls
  build.gradle.kts versionCode     the only thing the updater actually
                                   compares; must never go backwards

Run it standalone or from CI; it touches no database and needs no network.
"""
import io
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

fails = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (("   " + str(detail)) if detail else ""))
    if not cond:
        fails.append(name)


def read(*parts):
    # utf-8-sig: a file saved by a Windows editor carries a BOM, and a version
    # string with one in front of it compares unequal to the same digits
    return io.open(os.path.join(ROOT, *parts), encoding="utf-8-sig").read()


SEMVER = re.compile(r"^\d+\.\d+\.\d+$")

version = read("VERSION").strip()
gradle = read("android-app", "app", "build.gradle.kts")
manifest = json.loads(read("docs", "app", "latest.json"))

m = re.search(r'versionName\s*=\s*"([^"]+)"', gradle)
gradle_name = m.group(1) if m else None
m = re.search(r"versionCode\s*=\s*(\d+)", gradle)
gradle_code = int(m.group(1)) if m else None

print("1. Each source states a version at all")
check("VERSION is a semver", bool(SEMVER.match(version)), version)
check("gradle has a versionName", bool(gradle_name), gradle_name)
check("gradle has a versionCode", gradle_code is not None, gradle_code)
check("the manifest has both",
      bool(manifest.get("versionName")) and manifest.get("versionCode") is not None,
      manifest)

print()
print("2. They agree")
check("VERSION == android versionName", version == gradle_name,
      "%s vs %s" % (version, gradle_name))
check("VERSION == manifest versionName", version == manifest.get("versionName"),
      "%s vs %s" % (version, manifest.get("versionName")))
check("android versionCode == manifest versionCode",
      gradle_code == manifest.get("versionCode"),
      "%s vs %s" % (gradle_code, manifest.get("versionCode")))

print()
print("3. The manifest points somewhere that works")
url = manifest.get("apkUrl") or ""
# the asset is resolved by FILENAME inside whatever release is latest, so the
# name is load-bearing: attaching IT-Vault-v1.9.0.apk instead 404s this URL,
# the README badge and the site's download button all at once
check("the APK URL uses the stable latest-release form",
      url == "https://github.com/shatheitguy/it-vault/releases/latest/download/IT-Vault.apk",
      url)

print()
print("4. The image build will actually run")
wf = read(".github", "workflows", "docker-publish.yml")
check("it publishes semver image tags from a v* tag",
      "type=semver,pattern={{version}}" in wf)
check("it still tags latest on the default branch",
      "type=raw,value=latest,enable={{is_default_branch}}" in wf)
check("it triggers on v*.*.* tags", 'tags: [ "v*.*.*" ]' in wf)
# a workflow that names a branch which is no longer the default silently stops
# publishing -- which is exactly what happened when main was replaced
m = re.search(r"push:\s*\r?\n\s*#[^\n]*\r?\n(?:\s*#[^\n]*\r?\n)*\s*branches:\s*\[([^\]]*)\]", wf)
branches = m.group(1) if m else ""
check("it triggers on the current default branch",
      "main-fresh" in branches, branches.strip() or "no branches found")

print()
print("5. Nothing states a stale version anywhere else")
for path in ("README.md", "docs/index.html"):
    full = os.path.join(ROOT, path)
    if not os.path.exists(full):
        continue
    stale = []
    for line in read(path).splitlines():
        # "--tag 1.7.0" and "ITVAULT_TAG=1.6.1" are examples of how to pin an
        # image, not claims about the current release. An old number is
        # correct there -- the whole point of pinning is choosing your own.
        if any(k in line for k in ("--tag", "ITVAULT_TAG", "pin ")):
            continue
        for found in re.findall(r"\b1\.\d+\.\d+\b", line):
            if found != version and int(found.split(".")[1]) >= 6:
                stale.append(found + " -> " + line.strip()[:60])
    check("%s states no superseded release" % path, not stale, stale[:3])

print()
if fails:
    print("FAILED (%d): %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("ALL PASSED -- version %s is stated consistently" % version)
