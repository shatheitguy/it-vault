"""The MCP server only calls routes IT-Vault actually has.

The agent-facing tools in mcp/ talk to this same server over HTTP. That is a
seam with nothing holding it together: rename a route in app.py and the tools
keep compiling, keep loading, keep appearing in the agent's tool list, and
fail one at a time at the moment an agent reaches for them -- which is the
worst place to find out.

So this reads every path the MCP server calls out of its source and checks
each one against the routes app.py registers, method included. It needs
neither the mcp package nor a running server, so it runs in the ordinary
suite alongside everything else.

It also holds three properties of the tools themselves that matter more than
they look:

  * every asset write goes through the merge, because a PUT rewrites all
    seventeen columns and a partial body blanks the rest;
  * deleting is behind its own switch, so an agent cannot remove kit from the
    register because a sentence sounded like it should;
  * the API key travels as a header and is never interpolated into a path.
"""

import io
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SERVER = os.path.join(ROOT, "mcp", "itvault_mcp", "server.py")

fails = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (("   " + str(detail)) if detail else ""))
    if not cond:
        fails.append(name)


def read(path):
    return io.open(path, encoding="utf-8-sig").read()


if not os.path.exists(SERVER):
    print("mcp/itvault_mcp/server.py is missing -- nothing to check")
    sys.exit(1)

src = read(SERVER)
app = read(os.path.join(ROOT, "app.py"))

# ---- what app.py serves: (regex for the path, set of methods)
routes = []
for m in re.finditer(r'@app\.route\("([^"]+)"(?:,\s*methods=\[([^\]]*)\])?\)', app):
    path, methods = m.group(1), m.group(2) or '"GET"'
    verbs = set(re.findall(r'"([A-Z]+)"', methods)) or {"GET"}
    # <a_id>, <int:cid>, <path:ref> all match one segment of a real call
    pattern = re.sub(r"<[^>]+>", "[^/]+", path)
    routes.append((re.compile("^" + pattern + "$"), verbs, path))

# ---- what the MCP server calls: _call("METHOD", f"/api/...")
calls = []
for m in re.finditer(r'_call\(\s*"([A-Z]+)"\s*,\s*f?"([^"]+)"', src):
    method, path = m.group(1), m.group(2)
    # the f-string holes are single path segments too
    calls.append((method, re.sub(r"\{[^}]+\}", "x", path)))

print("\nevery route the tools call exists, with that method")
check("the tools call something at all", len(calls) >= 12, len(calls))
for method, path in sorted(set(calls)):
    hit = [(verbs, decl) for rx, verbs, decl in routes if rx.match(path)]
    if not hit:
        check("  %-6s %-34s" % (method, path), False, "no route in app.py matches")
        continue
    ok = any(method in verbs for verbs, _ in hit)
    check("  %-6s %-34s" % (method, path), ok,
          "" if ok else "route exists but allows %s" % sorted(hit[0][0]))

print("\nwrites cannot blank the fields they do not mention")
puts = re.findall(r'_call\(\s*"PUT"\s*,\s*f?"([^"]+)"', src)
check("the only asset PUT is inside the merge helper",
      all("/api/assets/" not in p or "_merge_put" in src.split(p)[0][-400:]
          for p in puts) or src.count('_call("PUT", f"/api/assets/') == 1,
      "a second PUT path would bypass the read-modify-write")
check("the merge starts from the stored record",
      "_merge_put" in src and "for k, v in asset.items()" in src)
for tool in ("update_asset", "assign_asset", "return_asset"):
    body = src.split("def %s(" % tool, 1)[1].split("\n@", 1)[0]
    check("  %-14s goes through the merge" % tool,
          "_merge_put" in body or "/checkin" in body, "writes directly")

print("\nthe dangerous one is behind its own switch")
body = src.split("def trash_asset(", 1)[1].split("\n@", 1)[0]
check("trash_asset refuses unless explicitly allowed",
      "ALLOW_DELETE" in body and "raise Fault" in body)
check("the switch is off unless set",
      'ITVAULT_MCP_ALLOW_DELETE" or ""' in src or
      re.search(r'ALLOW_DELETE\s*=.*or ""', src) is not None,
      "an unset variable must not read as enabled")
check("it is marked destructive for the runtime",
      "destructive_hint=True" in src,
      "runtimes use this to ask before running a tool")
check("read tools are marked read-only",
      src.count("annotations=READS") >= 8)

print("\nthe key is a header, not part of a URL")
check("the key is sent as X-Api-Key",
      '"X-Api-Key": KEY' in src)
check("the key is never interpolated into a path",
      not re.search(r'_call\([^)]*\{KEY\}', src) and "?key=" not in src)
check("nothing prints the key",
      not re.search(r'print\([^)]*KEY', src) and "KEY)" not in src.replace("or KEY)", ""))

print("\nand the agent is told what it is talking to")
check("there is a whoami tool", "def whoami(" in src)
check("it reports which server and which user",
      '"server": BASE' in src and '"user"' in src)
check("the server carries instructions for the model",
      "instructions=" in src and "find_employees" in src,
      "an agent that does not know EmployeeID exists will guess names")

print()
if fails:
    print("FAILED (%d): %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("ALL PASSED")
