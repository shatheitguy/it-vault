"""IT-Vault as an MCP server: tools an agent can use to run the estate.

Everything here goes through IT-Vault's own HTTP API with an API key, which
means an agent gets exactly the permissions of the user that key belongs to.
Give an agent a key from a read-only user and no amount of prompting will let
it change anything; give it an admin key and it can do what an admin can.
That is the intended safety boundary, and it is the server's rather than
this file's.

Two things are worth knowing before adding tools here.

**A PUT replaces the whole asset row.** `PUT /api/assets/<id>` writes every
column from the body, so a partial update silently blanks everything it
omits. An agent will absolutely send partial updates. So every write in here
reads the record first and overlays the change -- see `_merge_put`.

**An agent pays for every token it reads.** The API returns full rows with
fields no agent needs; the tools below trim to what is useful for deciding
what to do next, and cap list lengths. Full detail is one `get_asset` away.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

server = MCPServer(
    name="it-vault",
    instructions=(
        "IT-Vault is an IT asset register and helpdesk. Look things up with "
        "find_assets / get_asset, identify a printed tag with get_asset (it "
        "takes the code from the label), and use find_employees to turn a "
        "person's name into the EmployeeID that assign_asset needs. Every "
        "tool acts as the IT-Vault user whose API key this server holds, so a "
        "refusal is a permissions answer, not a bug -- call whoami."
    ),
)

# Hints the runtime can act on: a read tool is safe to retry or run
# speculatively, a destructive one is worth a confirmation prompt. Cheap to
# state and the difference between an agent that can be trusted with this and
# one that cannot.
READS = ToolAnnotations(read_only_hint=True, idempotent_hint=True)
WRITES = ToolAnnotations(read_only_hint=False, idempotent_hint=False)
DESTROYS = ToolAnnotations(read_only_hint=False, destructive_hint=True)

# ---------------------------------------------------------------- environment

BASE = (os.environ.get("ITVAULT_URL") or "").rstrip("/")
KEY = os.environ.get("ITVAULT_API_KEY") or ""
READONLY = (os.environ.get("ITVAULT_MCP_READONLY") or "").lower() in ("1", "true", "yes")
ALLOW_DELETE = (os.environ.get("ITVAULT_MCP_ALLOW_DELETE") or "").lower() in ("1", "true", "yes")
TIMEOUT = float(os.environ.get("ITVAULT_MCP_TIMEOUT") or 20)
# Only used by the HTTP transport, where the server is reachable by
# anything that can open a socket to it. See _http().
BEARER = (os.environ.get("ITVAULT_MCP_BEARER") or "").strip()

# One "HTTP Request: GET ..." line per call, in the agent's own log, for
# no benefit. Warnings and errors still come through.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# What a list returns per row. The full record has thirty-odd columns; these
# are the ones that answer "which one is this and what is going on with it".
ASSET_BRIEF = ("_id", "AssetTag", "Name", "Type", "Serial", "Status", "Location",
               "EmployeeID", "PublicCode")


class Fault(Exception):
    """Something the agent should be told in words rather than a traceback."""


def _client() -> httpx.Client:
    if not BASE:
        raise Fault("ITVAULT_URL is not set. Point it at the IT-Vault server, "
                    "e.g. http://itvault.lan:5000")
    if not KEY:
        raise Fault("ITVAULT_API_KEY is not set. Create one in IT-Vault under "
                    "Profile -> API key, using a user whose role has the access "
                    "this agent should have.")
    return httpx.Client(
        base_url=BASE,
        headers={"X-Api-Key": KEY, "Accept": "application/json"},
        timeout=TIMEOUT,
        follow_redirects=False,
    )


def _call(method: str, path: str, **kw) -> Any:
    if READONLY and method != "GET":
        raise Fault("This server is running read-only (ITVAULT_MCP_READONLY), "
                    "so nothing can be changed through it.")
    try:
        with _client() as c:
            r = c.request(method, path, **kw)
    except httpx.HTTPError as e:
        raise Fault(f"Could not reach IT-Vault at {BASE}: {e}") from e
    if r.status_code == 401:
        raise Fault("IT-Vault rejected the API key.")
    if r.status_code == 403:
        raise Fault("That key's role is not allowed to do this. Give the agent "
                    "a key from a user with the right module permission.")
    if r.status_code == 404:
        raise Fault("Not found.")
    if r.status_code >= 400:
        detail = ""
        try:
            detail = (r.json() or {}).get("error") or ""
        except ValueError:
            detail = (r.text or "")[:200]
        raise Fault(f"IT-Vault said no ({r.status_code}): {detail or 'no reason given'}")
    if not r.content:
        return {}
    try:
        return r.json()
    except ValueError:
        return {"text": r.text[:2000]}


def _brief(row: dict, keys=ASSET_BRIEF) -> dict:
    return {k: row.get(k, "") for k in keys if row.get(k) not in (None, "")}


def _resolve(ref: str) -> dict:
    """A tag, a public code or an id -> the full asset record.

    The server's own resolver does this, and it matches exactly rather than by
    substring, so "IT-10" never quietly resolves to IT-1004.
    """
    ref = (ref or "").strip()
    if not ref:
        raise Fault("Give an asset tag, the code from its printed label, or its id.")
    row = _call("GET", f"/api/assets/resolve/{ref}")
    if not isinstance(row, dict) or not row.get("_id"):
        raise Fault(f"No asset matches {ref!r}.")
    return row


# Fields the record carries but a PUT does not write: the server owns them,
# or they belong to their own endpoints. Sending them back is harmless -- the
# route only reads the columns it writes -- but SignatureData alone is a
# several-kilobyte data: URI on every update, and it ends up in logs.
NOT_WRITTEN_BY_PUT = ("SignatureData", "InvoiceFile", "PublicCode", "UpdatedAt",
                      "created_at", "is_deleted")


def _merge_put(asset: dict, changes: dict) -> dict:
    """Write `changes` onto an existing asset without losing the rest.

    PUT /api/assets/<id> rewrites every column from the body, so sending only
    the changed field blanks the others. This sends the record as it stands
    with the change laid over the top. Anything the record gains in future is
    forwarded too -- the exclusions are a short deny-list rather than a copy
    of the column list, which would go stale.
    """
    body = {k: v for k, v in asset.items()
            if not k.startswith("_") and k not in NOT_WRITTEN_BY_PUT}
    body.update({k: v for k, v in changes.items() if v is not None})
    return _call("PUT", f"/api/assets/{asset['_id']}", json=body)


# =============================================================== assets: read

@server.tool(annotations=READS)
def find_assets(query: str = "", status: str = "", limit: int = 25) -> dict:
    """Search the asset register.

    query matches name, tag, serial, model, location and the rest of the
    visible columns. status filters exactly (Available, Checked-Out,
    Under-Maintenance, Reserved, Retired, Lost/Stolen).
    """
    params = {}
    if query.strip():
        params["q"] = query.strip()
    if status.strip():
        params["status"] = status.strip()
    rows = _call("GET", "/api/assets", params=params)
    rows = rows if isinstance(rows, list) else []
    limit = max(1, min(int(limit or 25), 200))
    return {"count": len(rows), "showing": min(len(rows), limit),
            "assets": [_brief(r) for r in rows[:limit]]}


@server.tool(annotations=READS)
def get_asset(ref: str) -> dict:
    """Everything recorded about one asset.

    ref is its asset tag (IT-1042), the code printed on its QR label, or its
    id. The signature blob is dropped -- it is a data: URI hundreds of
    kilobytes long and of no use to an agent; ask for the links instead.
    """
    row = _resolve(ref)
    row.pop("SignatureData", None)
    return row


@server.tool(annotations=READS)
def asset_history(ref: str, limit: int = 20) -> dict:
    """Who changed what on this asset, newest first."""
    row = _resolve(ref)
    hist = _call("GET", f"/api/assets/{row['_id']}/history")
    hist = hist if isinstance(hist, list) else []
    limit = max(1, min(int(limit or 20), 100))
    return {"asset": row.get("AssetTag") or row["_id"],
            "changes": hist[:limit]}


@server.tool(annotations=READS)
def asset_links(ref: str) -> dict:
    """The addresses for one asset: its record, its printable label, and the
    public page a stranger reaches by scanning its tag."""
    row = _resolve(ref)
    code = (row.get("PublicCode") or "").strip()
    return {
        "asset": row.get("AssetTag") or row["_id"],
        "record": f"{BASE}/asset/{row['_id']}",
        "printable_label": f"{BASE}/label/{row['_id']}",
        "public_tag_page": f"{BASE}/p/{code}" if code else
                           "this asset has no public code yet; reprint its label",
    }


# ============================================================== assets: write

@server.tool(annotations=WRITES)
def create_asset(name: str, type: str = "", serial: str = "", manufacturer: str = "",
                 model: str = "", location: str = "", status: str = "Available",
                 employee_id: str = "", purchase_date: str = "",
                 warranty_months: int = 12, price: str = "", note: str = "") -> dict:
    """Add an asset to the register.

    Leave the tag alone -- the server allocates the next one in sequence.
    purchase_date is YYYY-MM-DD. warranty_months is months, not years.
    """
    if not name.strip():
        raise Fault("An asset needs a name.")
    body = {
        "Name": name.strip(), "Type": type.strip(), "Serial": serial.strip(),
        "Manufacturer": manufacturer.strip(), "Model": model.strip(),
        "Location": location.strip(), "Status": status.strip() or "Available",
        "EmployeeID": employee_id.strip(), "PurchaseDate": purchase_date.strip(),
        "WarrantyMonths": int(warranty_months or 0), "Price": price.strip(),
        "Note": note.strip(),
    }
    made = _call("POST", "/api/assets", json=body)
    new_id = (made or {}).get("_id") or (made or {}).get("id")
    return {"created": True, "id": new_id,
            "asset_tag": (made or {}).get("AssetTag", ""),
            "hint": "Print its label with asset_links, then stick it on the thing."}


@server.tool(annotations=WRITES)
def update_asset(ref: str, fields: dict) -> dict:
    """Change fields on an asset, leaving everything else as it was.

    fields uses the record's own names: Name, Type, Serial, Manufacturer,
    Model, Location, Status, EmployeeID, PurchaseDate, WarrantyMonths, Price,
    Note. Anything you do not mention keeps its current value.
    """
    if not isinstance(fields, dict) or not fields:
        raise Fault("Say which fields to change, e.g. {\"Location\": \"Store room B\"}.")
    row = _resolve(ref)
    unknown = [k for k in fields if k not in row]
    if unknown:
        raise Fault(f"Not fields on an asset: {', '.join(unknown)}. "
                    f"Call get_asset to see what it has.")
    _merge_put(row, fields)
    after = _resolve(ref)
    return {"updated": sorted(fields), "asset": _brief(after)}


@server.tool(annotations=WRITES)
def assign_asset(ref: str, employee_id: str) -> dict:
    """Give an asset to someone: sets the holder and marks it Checked-Out.

    employee_id is the directory's EmployeeID, not a person's name -- use
    find_employees to look one up. The server fills in who signed for it and
    when, and opens the checkout history entry.
    """
    if not employee_id.strip():
        raise Fault("Which employee? Pass an EmployeeID from find_employees.")
    row = _resolve(ref)
    _merge_put(row, {"EmployeeID": employee_id.strip(), "Status": "Checked-Out"})
    return {"assigned": _brief(_resolve(ref))}


@server.tool(annotations=WRITES)
def return_asset(ref: str, status: str = "Available") -> dict:
    """Take an asset back: clears the holder and closes the checkout entry.

    status is what it becomes -- Available normally, Under-Maintenance if it
    came back broken.
    """
    row = _resolve(ref)
    if not (row.get("Status") or "").lower() == "checked-out":
        return {"unchanged": True,
                "reason": f"{row.get('AssetTag')} is {row.get('Status')}, not Checked-Out."}
    _call("POST", f"/api/assets/{row['_id']}/checkin", json={})
    if status.strip() and status.strip() != "Available":
        _merge_put(_resolve(ref), {"Status": status.strip()})
    return {"returned": _brief(_resolve(ref))}


@server.tool(annotations=DESTROYS)
def trash_asset(ref: str) -> dict:
    """Move an asset to Trash, where it can still be restored.

    Refused unless the server was started with ITVAULT_MCP_ALLOW_DELETE=1.
    Removing kit from the register is not something an agent should be able to
    do because a sentence sounded like it.
    """
    if not ALLOW_DELETE:
        raise Fault("Deleting is switched off for this agent "
                    "(set ITVAULT_MCP_ALLOW_DELETE=1 to allow it).")
    row = _resolve(ref)
    _call("DELETE", f"/api/assets/{row['_id']}")
    return {"trashed": row.get("AssetTag") or row["_id"],
            "note": "Restorable from Trash in the web UI."}


# ==================================================================== tickets

@server.tool(annotations=READS)
def list_tickets(status: str = "", limit: int = 25) -> dict:
    """The helpdesk queue. status filters (Open, In-Progress, Resolved, Closed)."""
    rows = _call("GET", "/api/tickets")
    rows = rows if isinstance(rows, list) else []
    if status.strip():
        want = status.strip().lower()
        rows = [r for r in rows if (r.get("status") or "").lower() == want]
    limit = max(1, min(int(limit or 25), 200))
    keys = ("id", "code", "subject", "status", "priority", "category",
            "requester", "assignee", "created_at")
    return {"count": len(rows), "showing": min(len(rows), limit),
            "tickets": [_brief(r, keys) for r in rows[:limit]]}


@server.tool(annotations=READS)
def get_ticket(ticket_id: int) -> dict:
    """One ticket with its replies -- the conversation, not just the fields."""
    return _call("GET", f"/api/tickets/{int(ticket_id)}")


@server.tool(annotations=WRITES)
def create_ticket(subject: str, description: str = "", requester: str = "",
                  priority: str = "Normal", category: str = "",
                  asset_ref: str = "") -> dict:
    """Raise a ticket. asset_ref attaches it to an asset by tag, code or id."""
    if not subject.strip():
        raise Fault("A ticket needs a subject.")
    body = {"subject": subject.strip(), "description": description.strip(),
            "requester": requester.strip(), "priority": priority.strip() or "Normal",
            "category": category.strip(), "source": "Agent"}
    if asset_ref.strip():
        body["asset_id"] = _resolve(asset_ref)["_id"]
    made = _call("POST", "/api/tickets", json=body)
    t = (made or {}).get("ticket") or made or {}
    return {"created": True, "id": t.get("id"), "code": t.get("code", "")}


@server.tool(annotations=WRITES)
def reply_ticket(ticket_id: int, body: str) -> dict:
    """Add a reply to a ticket. It is visible to the requester on the portal,
    so write it as something a person will read."""
    if not body.strip():
        raise Fault("An empty reply is not a reply.")
    _call("POST", f"/api/tickets/{int(ticket_id)}/reply", json={"body": body.strip()})
    return {"replied": int(ticket_id)}


@server.tool(annotations=WRITES)
def set_ticket_status(ticket_id: int, status: str) -> dict:
    """Move a ticket: Open, In-Progress, Resolved or Closed."""
    if not status.strip():
        raise Fault("Which status?")
    _call("PUT", f"/api/tickets/{int(ticket_id)}", json={"status": status.strip()})
    return {"ticket": int(ticket_id), "status": status.strip()}


# ================================================== people, contracts, estate

@server.tool(annotations=READS)
def find_employees(query: str = "", limit: int = 50) -> dict:
    """The directory. Use this to turn a person's name into the EmployeeID that
    assign_asset wants."""
    rows = _call("GET", "/api/employees")
    rows = rows if isinstance(rows, list) else []
    if query.strip():
        q = query.strip().lower()
        rows = [r for r in rows if q in " ".join(
            str(r.get(k, "")) for k in ("EmployeeID", "EmpCode", "EmployeeName",
                                        "Department", "Designation", "Email")).lower()]
    limit = max(1, min(int(limit or 50), 200))
    keys = ("EmployeeID", "EmployeeName", "Department", "Designation", "Email")
    return {"count": len(rows), "showing": min(len(rows), limit),
            "employees": [_brief(r, keys) for r in rows[:limit]]}


@server.tool(annotations=READS)
def list_contracts(expiring_within_days: int = 0, limit: int = 50) -> dict:
    """Contracts, licences and subscriptions.

    expiring_within_days > 0 narrows it to the ones running out that soon,
    which is the question usually being asked.
    """
    rows = _call("GET", "/api/contracts")
    rows = rows if isinstance(rows, list) else []
    days = int(expiring_within_days or 0)
    if days > 0:
        import datetime
        cutoff = datetime.date.today() + datetime.timedelta(days=days)
        kept = []
        for r in rows:
            end = (r.get("end_date") or "")[:10]
            try:
                if datetime.date.fromisoformat(end) <= cutoff:
                    kept.append(r)
            except ValueError:
                continue
        rows = sorted(kept, key=lambda r: (r.get("end_date") or ""))
    limit = max(1, min(int(limit or 50), 200))
    keys = ("id", "name", "type", "vendor", "start_date", "end_date", "cost", "status")
    return {"count": len(rows), "showing": min(len(rows), limit),
            "contracts": [_brief(r, keys) for r in rows[:limit]]}


@server.tool(annotations=READS)
def estate_overview() -> dict:
    """The dashboard's numbers: totals by status and type, what is checked out,
    what is due back, which warranties and contracts are running out."""
    return _call("GET", "/api/dashboard")


# ============================================================== lost or found

@server.tool(annotations=READS)
def lost_and_found(status: str = "", limit: int = 25) -> dict:
    """Reports from people who scanned a tag: lost, found or returned."""
    rows = _call("GET", "/api/lostfound")
    rows = rows if isinstance(rows, list) else []
    if status.strip():
        want = status.strip().lower()
        rows = [r for r in rows if (r.get("status") or "").lower() == want]
    limit = max(1, min(int(limit or 25), 200))
    keys = ("id", "asset_tag", "status", "finder_name", "finder_mobile",
            "finder_note", "reported_at", "admin_note")
    return {"count": len(rows), "showing": min(len(rows), limit),
            "reports": [_brief(r, keys) for r in rows[:limit]]}


@server.tool(annotations=WRITES)
def set_lost_found_status(report_id: int, status: str, admin_note: str = "") -> dict:
    """Move a report to lost, found or returned.

    The asset follows: lost marks it Lost/Stolen, returned brings it back from
    that. So this is the tool for "we have it again", not update_asset.
    """
    want = (status or "").strip().lower()
    if want not in ("lost", "found", "returned"):
        raise Fault("status is lost, found or returned.")
    body = {"status": want}
    if admin_note.strip():
        body["admin_note"] = admin_note.strip()
    _call("PATCH", f"/api/lostfound/{int(report_id)}", json=body)
    return {"report": int(report_id), "status": want}


# ==================================================================== running

@server.tool(annotations=READS)
def whoami() -> dict:
    """Which IT-Vault this is connected to, as which user, and what this agent
    is allowed to do. Worth calling first when something is refused."""
    me = _call("GET", "/api/me")
    # /api/me answers with the identity under "user", and its payload also
    # contains the account's own api_key -- so pick fields rather than
    # forwarding the response, or the key ends up in the agent's transcript.
    return {
        "server": BASE,
        "user": (me or {}).get("user") or "",
        "role": (me or {}).get("role") or "",
        "writes": "disabled (read-only)" if READONLY else "enabled",
        "deleting": "enabled" if ALLOW_DELETE and not READONLY else "disabled",
        "note": "Permissions come from the key's own user in IT-Vault. This "
                "server cannot grant more than that user has.",
    }


def main() -> None:
    """Entry point for `itvault-mcp` and `python -m itvault_mcp`."""
    import json
    import sys

    if "--selftest" in sys.argv:
        # Answers "is this configured right" without an agent in the loop,
        # which is the first question when a tool call comes back refused.
        try:
            print(json.dumps(whoami(), indent=2))
        except Fault as e:
            print(f"not ready: {e}", file=sys.stderr)
            raise SystemExit(1)
        raise SystemExit(0)

    if "--http" in sys.argv:
        _http()
    else:
        server.run()


class _Bearer:
    """Require `Authorization: Bearer <token>` on the HTTP transport.

    Written as raw ASGI rather than a Starlette BaseHTTPMiddleware because
    this sits in front of a streaming endpoint, and BaseHTTPMiddleware
    buffers.
    """

    def __init__(self, app, token: str):
        self.app = app
        self.expected = f"Bearer {token}".encode()

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)
        got = dict(scope.get("headers") or {}).get(b"authorization", b"")
        # constant-time compare: this is a bearer token on an open port
        import hmac
        if not hmac.compare_digest(got, self.expected):
            body = b'{"error":"unauthorized"}'
            await send({"type": "http.response.start", "status": 401,
                        "headers": [(b"content-type", b"application/json"),
                                    (b"content-length", str(len(body)).encode())]})
            await send({"type": "http.response.body", "body": body})
            return
        return await self.app(scope, receive, send)


def _http() -> None:
    """Serve over HTTP for an agent that cannot spawn a process.

    ChatGPT is the reason this exists: it speaks only HTTP and needs a public
    HTTPS URL ending in /mcp, which is where this serves.

    The API key lives inside this process, so anything that can reach the
    port inherits every permission that key has. On loopback that is the
    machine's own business. Off loopback it is the internet's, so binding
    anywhere else without ITVAULT_MCP_BEARER is refused rather than served --
    a wrong default here is somebody else's asset register.
    """
    import sys

    host = os.environ.get("ITVAULT_MCP_HOST", "127.0.0.1")
    port = int(os.environ.get("ITVAULT_MCP_PORT", "8787"))
    loopback = host in ("127.0.0.1", "::1", "localhost")

    if not loopback and not BEARER:
        print(
            f"refusing to serve on {host}: anything that can reach that "
            f"address would get full use of the API key this process holds.\n"
            f"Set ITVAULT_MCP_BEARER to a long random token and send it as "
            f"Authorization: Bearer <token>, or bind to 127.0.0.1 and put a "
            f"tunnel in front.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    app = server.streamable_http_app(host=host)
    if BEARER:
        app = _Bearer(app, BEARER)
    else:
        print("serving on loopback with no bearer token; anything on this "
              "machine can use it", file=sys.stderr)

    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
