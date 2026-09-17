# IT-Vault as an MCP server

Gives an agent tools to run the estate: find a device, see who has it, assign
it, take it back, raise and answer tickets, check what contracts are running
out, and deal with the reports that come in when somebody scans a lost asset's
tag.

It is a thin layer over IT-Vault's own HTTP API. There is no second copy of
any logic here and no direct database access — which is what makes the
permission story simple.

## The permission story, first

Every call is made with an IT-Vault **API key**, and the agent gets exactly
the permissions of the user that key belongs to. Nothing in this server can
exceed them.

So decide what the agent is for, and give it a key to match:

| You want the agent to… | Give it a key from |
| --- | --- |
| answer questions, raise tickets | a user whose role has read on Assets |
| run the register day to day | a user with write on Assets and Tickets |
| everything, including deleting | an admin (and see the delete switch below) |

Create a key in IT-Vault: **Profile → API key → generate**. Treat it like a
password; it is one.

Two extra switches, because a role is coarser than intent:

- `ITVAULT_MCP_READONLY=1` — refuses every write regardless of what the key
  could do. For a watching agent.
- `ITVAULT_MCP_ALLOW_DELETE=1` — without this, `trash_asset` refuses.
  Removing kit from the register is not something an agent should do because
  a sentence sounded like it should.

Tools are also annotated for the runtime: reads are marked read-only and
idempotent, `trash_asset` is marked destructive, so an agent host that asks
before destructive tools will ask.

## Install

```bash
cd mcp
pip install -e .
```

That puts `itvault-mcp` on PATH. `python -m itvault_mcp` works too.

Check it can reach your server:

```bash
ITVAULT_URL=http://itvault.lan:5000 ITVAULT_API_KEY=your-key itvault-mcp --selftest
```

That prints the server, the user the key belongs to, its role, and whether
writes and deletes are enabled — or says what is wrong and exits non-zero:

```
not ready: ITVAULT_URL is not set. Point it at the IT-Vault server, …
not ready: Could not reach IT-Vault at http://itvault.lan:5000: …
not ready: IT-Vault rejected the API key.
```

It is the first thing to run when a tool call comes back refused. The same
answer is available to the agent itself, as the `whoami` tool.

## Wiring it to an agent

All three runtimes below take the same stdio shape: a command, its arguments,
and environment. **Point `command` at the real executable**, not at a shell —
Hermes in particular refuses an MCP entry whose command is a shell
interpreter with network egress in its arguments, and it is right to.

### Hermes

Config lives in `~/.hermes/config.yaml` under `mcp_servers`:

```yaml
mcp_servers:
  it-vault:
    command: itvault-mcp
    args: []
    env:
      ITVAULT_URL: http://itvault.lan:5000
      ITVAULT_API_KEY: ${ITVAULT_API_KEY}
```

Or interactively: `hermes mcp add`, then `hermes mcp test it-vault`.

Hermes supports `${VAR}` references in `env`, so the key can live in the
environment or its secret store rather than in the config file. Prefer that.

### OpenClaw

`~/.openclaw/openclaw.json`:

```json
{
  "mcpServers": {
    "it-vault": {
      "command": "itvault-mcp",
      "args": [],
      "transport": "stdio",
      "env": {
        "ITVAULT_URL": "http://itvault.lan:5000",
        "ITVAULT_API_KEY": "paste-the-key"
      }
    }
  }
}
```

The block is global; a per-agent config in that agent's directory overrides
it — which is how you give one agent a read-only key and another a write key.

### ZeroClaw

`~/.zeroclaw/config.toml`:

```toml
[mcp]
enabled = true

[[mcp.servers]]
name = "it-vault"
transport = "stdio"
command = "itvault-mcp"
args = []
env = { ITVAULT_URL = "http://itvault.lan:5000", ITVAULT_API_KEY = "paste-the-key" }
```

### An agent that is not on this machine

Run it over HTTP instead of stdio:

```bash
ITVAULT_URL=http://itvault.lan:5000 ITVAULT_API_KEY=… \
ITVAULT_MCP_HOST=127.0.0.1 ITVAULT_MCP_PORT=8787 \
itvault-mcp --http
```

Then point the runtime at `http://127.0.0.1:8787/mcp` with
`transport = "http"`. **Bind it to loopback or a trusted network only.** The
API key lives inside this process: anything that can reach the port inherits
it, and there is no second authentication step in front of it. If it has to
cross a network, put it behind something that authenticates — a reverse proxy
with a token, or a WireGuard tunnel.

## The tools

**Looking things up** — `find_assets`, `get_asset`, `asset_history`,
`asset_links`, `find_employees`, `list_contracts`, `list_tickets`,
`get_ticket`, `lost_and_found`, `estate_overview`, `whoami`

**Changing things** — `create_asset`, `update_asset`, `assign_asset`,
`return_asset`, `create_ticket`, `reply_ticket`, `set_ticket_status`,
`set_lost_found_status`

**Behind the delete switch** — `trash_asset`

Notes an agent benefits from, and which are in the tool descriptions too:

- `get_asset` takes an asset tag, the code printed on a QR label, or an id.
  Matching is exact, so `IT-10` never resolves to `IT-1004`.
- `assign_asset` wants an `EmployeeID`, not a person's name. That is what
  `find_employees` is for.
- `set_lost_found_status` is the tool for "we have it back", not
  `update_asset`: moving a report to `returned` brings the asset out of
  Lost/Stolen by itself.
- `update_asset` takes only the fields you are changing. Everything else
  keeps its value.

That last one is the whole reason this server exists rather than letting an
agent call the API directly: `PUT /api/assets/<id>` rewrites all seventeen
columns from the body, so a partial update sent straight at the API blanks
the serial, the location and the holder. Every write here reads the record
first and lays the change on top.

## Tests

```bash
cd mcp && python test_server.py
```

A stub HTTP server stands in for IT-Vault, so nothing touches real data. It
checks the merge (the PUT body must still carry every field the record had),
the two switches, error handling, and that the key only ever travels as a
header.

`tests/test_mcp_contract.py`, in the main suite, checks the other half: that
every route these tools call exists in `app.py` with that method. Rename a
route and that test fails immediately rather than an agent discovering it
mid-task.
