# IT-Vault -- self-hosted IT asset and helpdesk manager.
# Copyright (C) 2026 Sharqan Ahamed (Sha The IT Guy)
#
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The WhatsApp link, from the Python side.

WhatsApp Web's protocol lives in Baileys, a Node library, so the actual
connection runs in whatsapp/bridge.mjs. This module starts that helper on
demand, hands it a random port-local token and a key derived from the
server's own secret (it encrypts the linked device's keys with it), and
talks to it over 127.0.0.1.

Nothing here ever raises into a caller: a WhatsApp that is not set up, not
installed or not linked is reported as a status, and a send that cannot go
returns a reason. The email path next to it must never be the thing that
breaks because WhatsApp did.
"""
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import urllib.request

_BASE = os.path.dirname(os.path.abspath(__file__))
BRIDGE_DIR = os.path.join(_BASE, "whatsapp")
BRIDGE = os.path.join(BRIDGE_DIR, "bridge.mjs")

_lock = threading.Lock()
_st = {"proc": None, "port": 0, "token": "", "auth_dir": "", "key": ""}


def configure(data_dir, secret):
    """Where the linked device's keys live, and the secret they are locked
    with. Called once by app.py at import."""
    _st["auth_dir"] = os.path.join(data_dir, "whatsapp")
    _st["key"] = hashlib.sha256(("itvault-whatsapp:" + str(secret)).encode()).hexdigest()


def _node():
    return shutil.which("node") or shutil.which("node.exe")


def installed():
    """'' when the helper can run, else the reason it can't -- shown as-is."""
    if not _node():
        return "Node.js is not installed on this server, so WhatsApp can't run. Install Node.js 20 or newer, then restart IT-Vault."
    if not os.path.isdir(os.path.join(BRIDGE_DIR, "node_modules", "@whiskeysockets", "baileys")):
        return "The WhatsApp component is not installed. In the IT-Vault folder run:  cd whatsapp && npm ci --omit=dev  then restart IT-Vault."
    return ""


def has_link():
    """Linked before: worth bringing the helper up at start so sends work."""
    d = _st["auth_dir"]
    return bool(d) and os.path.exists(os.path.join(d, "creds.json"))


def _alive():
    p = _st["proc"]
    return p is not None and p.poll() is None and _st["port"]


def _spawn():
    """Start the helper and wait for the line that says which port it got."""
    env = dict(os.environ)
    token = secrets.token_hex(24)
    env.update({"WA_PORT": "0", "WA_TOKEN": token, "WA_DIR": _st["auth_dir"],
                "WA_KEY": _st["key"], "ITVAULT_PPID": str(os.getpid())})
    kw = {}
    if sys.platform == "win32":
        kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    p = subprocess.Popen([_node(), BRIDGE], cwd=BRIDGE_DIR, env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, text=True, encoding="utf-8",
                         errors="replace", bufsize=1, **kw)
    port = 0
    deadline = time.time() + 20
    while time.time() < deadline:
        line = p.stdout.readline()
        if not line:
            break
        print(line.rstrip(), flush=True)
        m = re.search(r"listening on 127\.0\.0\.1:(\d+)", line)
        if m:
            port = int(m.group(1)); break
    if not port:
        try: p.kill()
        except Exception: pass
        return False
    # keep echoing what the helper says into the server log
    def _pump(stream):
        try:
            for ln in stream:
                print(ln.rstrip(), flush=True)
        except Exception:
            pass
    threading.Thread(target=_pump, args=(p.stdout,), daemon=True).start()
    _st.update(proc=p, port=port, token=token)
    return True


def _ensure():
    with _lock:
        if _alive():
            return True
        if installed() or not _st["auth_dir"]:
            return False
        try:
            return _spawn()
        except Exception as e:
            print("[whatsapp] could not start the helper:", e, flush=True)
            return False


def _call(method, path, payload=None, timeout=15):
    if not _ensure():
        return None
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{_st['port']}{path}", data=data, method=method,
                                 headers={"x-wa-token": _st["token"], "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode() or "{}")
    except Exception as e:
        print(f"[whatsapp] {path}: {e}", flush=True)
        return None


def shutdown():
    """Stop the helper (before this process re-execs itself)."""
    with _lock:
        p = _st["proc"]
        _st.update(proc=None, port=0, token="")
    if p is not None and p.poll() is None:
        try:
            p.terminate(); p.wait(timeout=5)
        except Exception:
            try: p.kill()
            except Exception: pass


def resume():
    """At server start: linked before -> connect again, in the background."""
    if has_link() and not installed():
        threading.Thread(target=_ensure, daemon=True).start()


def status():
    why = installed()
    if why:
        return {"status": "unavailable", "error": why, "qr": None, "me": None}
    if not _alive() and not has_link():
        return {"status": "off", "qr": None, "me": None, "error": None}
    r = _call("GET", "/status")
    return r or {"status": "off", "qr": None, "me": None, "error": "The WhatsApp helper did not answer. See the server log."}


def start():
    why = installed()
    if why:
        return {"status": "unavailable", "error": why}
    return _call("POST", "/start", {}) or {"status": "off", "error": "The WhatsApp helper did not start. See the server log."}


def logout():
    if not _alive():
        # not running: just forget the saved link
        try: shutil.rmtree(_st["auth_dir"], ignore_errors=True)
        except Exception: pass
        return {"status": "off"}
    return _call("POST", "/logout", {}) or {"status": "off"}


def is_on():
    if not _alive():
        return False
    r = _call("GET", "/status", timeout=5)
    return bool(r and r.get("status") == "on")


def normalize(phone, country_code="971"):
    """A phone number as WhatsApp wants it: country code + number, digits only.

    '+971 50 123 4567' and '00971501234567' are already international.
    '050 123 4567' or '501234567' is local, and gets the install's default
    country code in place of the leading zero. Anything that does not come out
    8-15 digits long is not a number, and '' is returned.
    """
    raw = str(phone or "").strip()
    cc = re.sub(r"\D", "", str(country_code or ""))
    d = re.sub(r"\D", "", raw)
    if not d:
        return ""
    if raw.startswith("+"):
        pass
    elif d.startswith("00"):
        d = d[2:]
    elif cc and d.startswith(cc) and len(d) >= len(cc) + 8:
        pass
    elif cc:
        d = cc + d.lstrip("0")
    return d if 8 <= len(d) <= 15 else ""


def send(number, text="", pdf=None, file_name="", timeout=60):
    """'ok' | 'not_linked' | 'not_on_whatsapp' | 'bad_number' | 'failed' | 'unavailable'."""
    if installed():
        return "unavailable"
    if not number:
        return "bad_number"
    payload = {"number": number, "text": text}
    if pdf:
        import base64
        payload.update(document=base64.b64encode(pdf).decode(), fileName=file_name or "document.pdf", caption=text)
    r = _call("POST", "/send", payload, timeout=timeout)
    return (r or {}).get("result") or "failed"
