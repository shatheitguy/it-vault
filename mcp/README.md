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

Everything except ChatGPT takes the same stdio shape -- a command, its
arguments, and environment -- in each runtime's own file. **Point `command`
at the real executable**, not at a shell: Hermes refuses an MCP entry whose
command is a shell interpreter with network egress in its arguments, and it
is right to.

ChatGPT cannot spawn a process at all, so it gets the HTTP transport; its
section says what that costs.

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

### Claude Desktop

`claude_desktop_config.json` — on Windows `%APPDATA%\Claude\`, on macOS
`~/Library/Application Support/Claude/`:

```json
{
  "mcpServers": {
    "it-vault": {
      "command": "itvault-mcp",
      "args": [],
      "env": {
        "ITVAULT_URL": "http://itvault.lan:5000",
        "ITVAULT_API_KEY": "paste-the-key"
      }
    }
  }
}
```

Restart Claude Desktop; the tools appear under the tools icon. If `command`
cannot be found, give the absolute path — a desktop app does not inherit the
PATH your shell has (`where itvault-mcp` / `which itvault-mcp` tells you it).

### Claude Code

One command, from anywhere:

```bash
claude mcp add it-vault   --env ITVAULT_URL=http://itvault.lan:5000   --env ITVAULT_API_KEY=your-key   -- itvault-mcp
```

Add `-s user` to make it available in every project rather than this one.
`claude mcp list` shows whether it connected.

### Claude (claude.ai and the desktop app) — as a connector

The Connectors dialog you see in Claude has two halves, and only one of them
is yours to fill:

- **Add** (top right) — a custom connector, which is what you want. Claude
  dials your MCP server **from Anthropic's cloud**, so `localhost` is no use
  here: it has to be reachable over the public internet on HTTPS.
- **Discover / Directory** — a catalogue Anthropic curates. Nothing you write
  puts an entry there; it is a submission and a review. Same for ChatGPT's
  app directory. Everything below is the first half, which works today.

Run the HTTP transport with a token:

```bash
export ITVAULT_URL=http://itvault.lan:5000
export ITVAULT_API_KEY=your-key
export ITVAULT_MCP_BEARER="$(openssl rand -hex 32)"
itvault-mcp --http                     # 127.0.0.1:8787/mcp
```

Publish it on a name you own, without opening a port — you already run
Cloudflare:

```bash
cloudflared tunnel --url http://127.0.0.1:8787
```

Then **Settings → Connectors → Add custom connector**, paste
`https://your-name/mcp`, and give it the token:

- If your organisation has the **Request headers** section in that dialog,
  add `Authorization: Bearer <your token>`. It is a beta and not every
  organisation has it yet.
- If you do not see that section, do not fall back to running it open.
  Authenticate at the edge instead: a Cloudflare Access service token, or any
  reverse proxy that checks a header of its own and injects the
  `Authorization` header before passing the request on. The server still
  refuses anything without the bearer, so the proxy is the only thing that
  can reach it.

The properly supported route is OAuth, which this server does not implement.
It is worth doing if this ends up serving more than your own agents, and it
is the only option that avoids a long-lived shared token.

### ChatGPT

ChatGPT is the odd one out: it speaks only HTTP, cannot spawn a local
process, and wants a **public HTTPS URL ending in `/mcp`**. So this runs in
HTTP mode, behind a token, behind TLS:

```bash
export ITVAULT_URL=http://itvault.lan:5000
export ITVAULT_API_KEY=your-key
export ITVAULT_MCP_BEARER="$(openssl rand -hex 32)"   # keep this
itvault-mcp --http            # serves 127.0.0.1:8787/mcp
```

Put it behind something that terminates TLS on a name you own — a reverse
proxy, or a tunnel — then in ChatGPT: **Settings → Apps & Connectors →
Advanced → Developer mode**, then **Add custom connector**, with:

- **URL** — `https://your-host/mcp` (the `/mcp` matters; without it the
  connector fails to list tools)
- **Authentication** — Token, and paste the `ITVAULT_MCP_BEARER` value

Developer mode is on paid plans only.

Two things this server does so that exposure is a decision rather than an
accident:

- Binding anywhere other than loopback **without** `ITVAULT_MCP_BEARER` is
  refused, with an explanation, rather than served. The API key lives in this
  process; anything that can reach the port inherits every permission it has.
- With the token set, every request without a matching
  `Authorization: Bearer` gets a 401 before it reaches any tool.

Neither is a substitute for TLS. Over plain HTTP the token crosses the
network in the clear, so terminate HTTPS in front of it, and prefer a tunnel
to opening a port.

### Anything else that speaks MCP

There is nothing special about the runtimes above. A client that spawns a
process wants `itvault-mcp`, with `ITVAULT_URL` and `ITVAULT_API_KEY` in its
environment. A client that connects over the network wants:

```bash
ITVAULT_URL=http://itvault.lan:5000 ITVAULT_API_KEY=your-key ITVAULT_MCP_HOST=127.0.0.1 ITVAULT_MCP_PORT=8787 itvault-mcp --http
```

and a URL ending in `/mcp` — `http://127.0.0.1:8787/mcp` here. That is the
whole interface.

On loopback that is all there is to it. To reach it from anywhere else, set
`ITVAULT_MCP_BEARER` and send it as `Authorization: Bearer <token>`: without
that, binding off loopback is refused outright, because the API key lives
inside this process and anything that can reach the port inherits every
permission it has. Terminate TLS in front of it either way — a bearer token
over plain HTTP is a bearer token on the wire.

If a runtime refuses to start it, the usual causes, in order: `itvault-mcp`
not on that program's PATH (give the absolute path), the key not reaching the
process (check how that runtime passes environment), or the runtime blocking
the command for looking like a shell wrapper. `itvault-mcp --selftest` in the
same shell tells you which half is wrong.

## Every setting

| Variable | Default | What it does |
| --- | --- | --- |
| `ITVAULT_URL` | — | Where IT-Vault is. Required. |
| `ITVAULT_API_KEY` | — | The key every call is made with. Required. It decides what the agent can do. |
| `ITVAULT_MCP_READONLY` | off | Refuses every write, whatever the key could do. |
| `ITVAULT_MCP_ALLOW_DELETE` | off | Required for `trash_asset`. |
| `ITVAULT_MCP_TIMEOUT` | `20` | Seconds to wait on IT-Vault before giving up. |
| `ITVAULT_MCP_HOST` | `127.0.0.1` | HTTP transport only. Off loopback needs a bearer token. |
| `ITVAULT_MCP_PORT` | `8787` | HTTP transport only. |
| `ITVAULT_MCP_BEARER` | — | HTTP transport only. Requires `Authorization: Bearer <token>` on every request. |

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
