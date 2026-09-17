"""The Unraid and TrueNAS templates still describe this app.

A NAS template is a copy of the app's configuration living outside the app,
and copies rot: a variable gets renamed here, a path moves there, and the
template keeps saying the old thing. Nobody notices, because the people it
breaks are strangers installing it for the first time -- who conclude the
software does not work and move on.

So this checks the templates against the code rather than against each other:
every environment variable they set is one app.py actually reads, every path
they mount is one the app actually writes, and both of them name the same
published image.
"""

import io
import os
import re
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

fails = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (("   " + str(detail)) if detail else ""))
    if not cond:
        fails.append(name)


def read(*parts):
    return io.open(os.path.join(ROOT, *parts), encoding="utf-8-sig").read()


app_src = read("app.py")
IMAGE = "ghcr.io/shatheitguy/it-vault"

# What the app is actually willing to read, and where it actually writes.
app_env = set(re.findall(r'(?:os\.environ\.get|_env)\(\s*"([A-Z][A-Z0-9_]+)"', app_src))
APP_PATHS = ("/app/data", "/app/invoices", "/app/backups")

print("\nthe Unraid template")
try:
    tpl = ET.fromstring(read("unraid", "it-vault.xml"))
    parsed = True
except ET.ParseError as e:
    tpl, parsed = None, False
    check("it is valid XML", False, e)

if parsed:
    check("it is valid XML", True)
    check("it declares the v2 container format", tpl.get("version") == "2", tpl.get("version"))
    for tag in ("Name", "Repository", "Registry", "Overview", "Category", "WebUI",
                "Icon", "Support", "Project", "TemplateURL"):
        el = tpl.find(tag)
        check("  <%s>" % tag, el is not None and (el.text or "").strip() != "")

    check("it points at the published image",
          (tpl.findtext("Repository") or "").strip() == IMAGE,
          tpl.findtext("Repository"))
    check("the WebUI opens the right port", "[PORT:5000]" in (tpl.findtext("WebUI") or ""))
    check("it does not ask for privileged",
          (tpl.findtext("Privileged") or "false").lower() == "false")

    icon = (tpl.findtext("Icon") or "")
    check("the icon is a raw URL to a file that exists in this repo",
          icon.endswith("default_icon.png") and
          os.path.exists(os.path.join(ROOT, "default_icon.png")), icon)
    turl = (tpl.findtext("TemplateURL") or "")
    check("TemplateURL points at this very file",
          turl.endswith("unraid/it-vault.xml") and
          os.path.exists(os.path.join(ROOT, "unraid", "it-vault.xml")), turl)
    check("both URLs use the one branch, not a stale one",
          "/main/" in icon and "/main/" in turl,
          "a template that fetches from a dead branch shows a broken icon for ever")

    configs = tpl.findall("Config")
    check("it exposes a port, three paths and the database settings",
          len(configs) >= 9, "%d Config entries" % len(configs))

    tpl_vars = {c.get("Target") for c in configs if c.get("Type") == "Variable"}
    unknown = sorted(v for v in tpl_vars if v not in app_env)
    check("every variable it sets is one the app reads", not unknown, unknown)

    tpl_paths = {c.get("Target") for c in configs if c.get("Type") == "Path"}
    check("it mounts exactly the paths the app writes",
          tpl_paths == set(APP_PATHS), sorted(tpl_paths))

    masked = {c.get("Target") for c in configs if (c.get("Mask") or "").lower() == "true"}
    check("the password fields are masked", {"DB_PASS", "ITVAULT_SECRET"} <= masked, sorted(masked))

    overview = (tpl.findtext("Overview") or "")
    check("it says the app brings no database",
          "MariaDB" in overview and "DATABASE" in overview.upper(),
          "someone installing this needs to know before they start")

print("\nthe maintainer profile Community Applications asks for")
try:
    prof = ET.fromstring(read("unraid", "ca_profile.xml"))
    check("it is valid XML", True)
    check("it carries a non-empty Profile",
          (prof.findtext("Profile") or "").strip() != "")
    check("and an icon", (prof.findtext("Icon") or "").strip() != "")
except (ET.ParseError, FileNotFoundError) as e:
    check("ca_profile.xml is present and valid", False, e)

print("\nthe TrueNAS compose")
compose = read("truenas", "docker-compose.yaml")
try:
    import yaml
    doc = yaml.safe_load(compose)
    check("it is valid YAML", isinstance(doc, dict) and "services" in doc)
except ImportError:
    doc = None
    print("  (pyyaml not installed -- falling back to text checks)")

if doc:
    svcs = doc["services"]
    check("it brings a database with it", any("mariadb" in (s.get("image") or "")
                                              for s in svcs.values()),
          "on a NAS, an app that needs a database you have not built yet is one nobody finishes installing")
    app = next((s for s in svcs.values() if IMAGE in (s.get("image") or "")), None)
    check("it runs the published image", app is not None)
    if app:
        env = app.get("environment") or {}
        unknown = sorted(k for k in env if k not in app_env)
        check("every variable it sets is one the app reads", not unknown, unknown)
        mounts = [v.split(":")[-1] for v in (app.get("volumes") or [])]
        check("it persists all three paths", set(APP_PATHS) <= set(mounts), mounts)
        check("the app waits for the database to be healthy",
              (app.get("depends_on") or {}).get("itvault-db", {}).get("condition")
              == "service_healthy",
              "otherwise first start races the schema build")
        check("it does not redefine the image's healthcheck",
              "healthcheck" not in app,
              "there is no /healthz endpoint; a second definition only rots")

print("\nboth of them agree with each other")
check("same image in both", IMAGE in compose and (tpl is None or
      (tpl.findtext("Repository") or "").strip() == IMAGE))
check("neither ships a password that would work",
      "change-me" in compose and "ITVAULT_ADMIN_PASS" not in (
          tpl.findtext("Overview") if tpl is not None else ""),
      "no default admin password anywhere; the wizard asks")

print()
if fails:
    print("FAILED (%d): %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("ALL PASSED")
