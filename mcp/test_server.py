"""The MCP server's own tests, against a stand-in IT-Vault.

Run with the package installed (pip install -e .):

    python test_server.py

There is no IT-Vault here: a stub HTTP server answers the handful of routes
the tools use and records every request, so the things worth checking can be
checked without touching anyone's data.

The one that matters most is the merge. `PUT /api/assets/<id>` rewrites every
column from the body, so a tool that forwards an agent's partial update
blanks every field the agent did not mention -- serial, location, who has it.
That is data loss caused by a tool being convenient, and the test below fails
if the PUT body is ever missing a field the record already had.
"""

import importlib
import json
import os
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

fails = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + (("   " + str(detail)) if detail else ""))
    if not cond:
        fails.append(name)


def _refused(module, call):
    """True if `call` was turned down with a readable message."""
    try:
        call()
    except module.Fault:
        return True
    except Exception as e:                      # anything else is a bug
        print("      (raised %s instead of Fault: %s)" % (type(e).__name__, e))
        return False
    return False


# --------------------------------------------------------------- the stand-in

ASSET = {
    "_id": "abc123", "AssetTag": "IT-1042", "Name": "Dell Latitude 5440",
    "Type": "Laptop", "Serial": "7XJ4K93", "MacAddress": "A4:BB:6D:11:02:9F",
    "Manufacturer": "Dell", "Model": "Latitude 5440", "Location": "Head Office",
    "Status": "Available", "EmployeeID": "", "PurchaseDate": "2026-02-11",
    "WarrantyMonths": 36, "Price": "4250", "Note": "boxed",
    "ReceivedBy": "", "NotesReceived": "", "PublicCode": "mfqx7t2v",
    "SignatureData": "data:image/png;base64," + "A" * 4000,
}

seen = []          # every request the tools made, in order


class Stub(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return {}

    def do_GET(self):
        seen.append(("GET", self.path, None, dict(self.headers)))
        if self.path.startswith("/api/assets/resolve/"):
            ref = self.path.rsplit("/", 1)[-1]
            if ref in (ASSET["_id"], ASSET["AssetTag"], ASSET["PublicCode"]):
                return self._send(200, ASSET)
            return self._send(404, {"error": "That tag is not in this install."})
        if self.path.startswith("/api/assets?") or self.path == "/api/assets":
            return self._send(200, [ASSET])
        if self.path == "/api/me":
            # the real route answers with "user", and includes the account's
            # own api_key -- both of which whoami has to handle correctly
            return self._send(200, {"user": "agent", "role": "editor",
                                    "api_key": "test-key"})
        if self.path.endswith("/history"):
            return self._send(200, [{"field": "Status", "old_val": "Available",
                                     "new_val": "Checked-Out", "user": "sha",
                                     "ts": "2026-09-17 09:00"}])
        if self.path == "/api/employees":
            return self._send(200, [{"EmployeeID": "EMP-204", "EmployeeName": "A. Fernandes",
                                     "Department": "Operations", "Email": "a@example.com",
                                     "EmpCode": "204"}])
        if self.path == "/api/lostfound":
            return self._send(200, [{"id": 7, "asset_tag": "IT-1042", "status": "found",
                                     "finder_name": "Courier", "finder_mobile": "+9715..."}])
        return self._send(404, {"error": "no such route in the stub"})

    def do_PUT(self):
        body = self._read()
        seen.append(("PUT", self.path, body, dict(self.headers)))
        ASSET.update({k: v for k, v in body.items() if k in ASSET})
        return self._send(200, {"ok": True})

    def do_POST(self):
        body = self._read()
        seen.append(("POST", self.path, body, dict(self.headers)))
        if self.path.endswith("/checkin"):
            ASSET["Status"] = "Available"
            ASSET["EmployeeID"] = ""
            return self._send(200, {"ok": True})
        return self._send(200, {"ok": True, "_id": "new1", "AssetTag": "IT-1043"})

    def do_DELETE(self):
        seen.append(("DELETE", self.path, None, dict(self.headers)))
        return self._send(200, {"ok": True})

    def do_PATCH(self):
        body = self._read()
        seen.append(("PATCH", self.path, body, dict(self.headers)))
        return self._send(200, {"ok": True})


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


PORT = free_port()
httpd = HTTPServer(("127.0.0.1", PORT), Stub)
threading.Thread(target=httpd.serve_forever, daemon=True).start()


def load(**env):
    """Import the server with a given environment. It reads its settings at
    import time, which is what a runtime does when it spawns it."""
    os.environ["ITVAULT_URL"] = f"http://127.0.0.1:{PORT}"
    os.environ["ITVAULT_API_KEY"] = "test-key"
    for k in ("ITVAULT_MCP_READONLY", "ITVAULT_MCP_ALLOW_DELETE"):
        os.environ.pop(k, None)
    os.environ.update(env)
    name = "itvault_mcp.server"
    if name in sys.modules:
        return importlib.reload(sys.modules[name])
    return importlib.import_module(name)


try:
    srv = load()

    print("\nfinding things")
    out = srv.find_assets(query="latitude")
    check("find_assets returns the match", out["count"] == 1 and
          out["assets"][0]["AssetTag"] == "IT-1042", out)
    check("it sends the query as q=", any(p.startswith("/api/assets?q=") for _, p, _, _ in seen),
          [p for m, p, _, _ in seen if m == "GET"])
    check("a list row is trimmed, not the whole record",
          "SignatureData" not in out["assets"][0] and "Note" not in out["assets"][0],
          list(out["assets"][0]))

    print("\nidentifying a scanned tag")
    for ref in ("IT-1042", "mfqx7t2v", "abc123"):
        got = srv.get_asset(ref)
        check("  %-9s resolves" % ref, got.get("_id") == "abc123")
    check("the signature blob is not handed to the agent",
          "SignatureData" not in srv.get_asset("IT-1042"),
          "it is a 4KB+ data: URI of no use to a model")
    try:
        srv.get_asset("IT-99999")
        check("an unknown tag is an error, not an empty answer", False)
    except srv.Fault as e:
        check("an unknown tag is an error, not an empty answer", True, str(e)[:40])

    print("\nupdating without losing the rest of the record")
    seen.clear()
    srv.update_asset("IT-1042", {"Location": "Store room B"})
    put = [(p, b) for m, p, b, _ in seen if m == "PUT"]
    check("it does one PUT", len(put) == 1, [p for p, _ in put])
    body = put[0][1]
    missing = [k for k in ("Name", "Serial", "Type", "Manufacturer", "PurchaseDate",
                           "WarrantyMonths", "Price", "Note", "MacAddress")
               if k not in body]
    check("the PUT carries every field the record had", not missing,
          "missing: %s -- this is the whole reason _merge_put exists" % missing)
    check("and the change is applied", body.get("Location") == "Store room B")
    check("it reads before it writes",
          [m for m, _, _, _ in seen][0] == "GET",
          [m for m, _, _, _ in seen])
    try:
        srv.update_asset("IT-1042", {"Colour": "black"})
        check("a field that does not exist is refused", False)
    except srv.Fault as e:
        check("a field that does not exist is refused", "Colour" in str(e), str(e)[:60])

    print("\nassigning and taking back")
    seen.clear()
    srv.assign_asset("IT-1042", "EMP-204")
    put = [b for m, _, b, _ in seen if m == "PUT"]
    check("assigning sets holder and status together",
          put and put[0].get("EmployeeID") == "EMP-204" and
          put[0].get("Status") == "Checked-Out",
          {k: put[0].get(k) for k in ("EmployeeID", "Status")} if put else None)
    check("a PUT does not ship the signature blob",
          put and "SignatureData" not in put[0],
          "several kilobytes of data: URI that the route ignores anyway")
    check("assigning without an employee is refused",
          _refused(srv, lambda: srv.assign_asset("IT-1042", " ")))
    seen.clear()
    srv.return_asset("IT-1042")
    check("returning uses the check-in route",
          any(p.endswith("/checkin") for m, p, _, _ in seen if m == "POST"),
          [p for m, p, _, _ in seen])
    out = srv.return_asset("IT-1042")
    check("returning something already back changes nothing",
          out.get("unchanged") is True, out)

    print("\nthe tickets and the rest")
    check("list_tickets survives a server with no tickets route",
          _refused(srv, lambda: srv.list_tickets()),
          "the stub has no /api/tickets, so this must be an error not a crash")
    check("find_employees filters by name",
          srv.find_employees(query="fernandes")["count"] == 1)
    check("lost_and_found reads the reports",
          srv.lost_and_found()["reports"][0]["id"] == 7)
    seen.clear()
    srv.set_lost_found_status(7, "returned", admin_note="back from the courier")
    patch = [b for m, _, b, _ in seen if m == "PATCH"]
    check("a report moves with a PATCH", patch and patch[0]["status"] == "returned", patch)
    check("an invented status is refused",
          _refused(srv, lambda: srv.set_lost_found_status(7, "mislaid")))

    print("\nthe key travels as a header, never in the URL")
    hdrs = [h for _, _, _, h in seen]
    check("every request carried X-Api-Key",
          all(h.get("X-Api-Key") == "test-key" for h in hdrs), len(hdrs))
    check("no request put the key in the path",
          not any("test-key" in p for _, p, _, _ in seen))

    print("\nthe two gates")
    srv_ro = load(ITVAULT_MCP_READONLY="1")
    check("read-only refuses a write",
          _refused(srv_ro, lambda: srv_ro.update_asset("IT-1042", {"Note": "x"})))
    check("read-only still reads", srv_ro.find_assets()["count"] == 1)
    srv_w = load()
    check("deleting is off by default",
          _refused(srv_w, lambda: srv_w.trash_asset("IT-1042")))
    srv_d = load(ITVAULT_MCP_ALLOW_DELETE="1")
    seen.clear()
    srv_d.trash_asset("IT-1042")
    check("deleting works when it is switched on",
          any(m == "DELETE" for m, _, _, _ in seen))
    who = srv_d.whoami()
    check("whoami reports the gates",
          who["deleting"] == "enabled" and who["role"] == "editor", who)
    check("whoami names the user it is acting as", who["user"] == "agent", who)
    check("whoami does not leak the key back to the agent",
          "test-key" not in json.dumps(who),
          "/api/me includes api_key, so whoami must pick fields not forward them")
finally:
    httpd.shutdown()

print()
if fails:
    print("FAILED (%d): %s" % (len(fails), ", ".join(fails)))
    sys.exit(1)
print("ALL PASSED")
