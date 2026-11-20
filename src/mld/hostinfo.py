"""Talking to the host: pair data, address normalisation, reachability."""

from __future__ import annotations

import json
import socket
import subprocess
import urllib.parse
from typing import Iterable, List, Tuple


def split_host(value: str, default_port: int = 4939) -> Tuple[str, int]:
    raw = value.strip()
    if "://" in raw:
        u = urllib.parse.urlsplit(raw)
        return (u.hostname or "", u.port or default_port)
    raw = raw.rstrip("/").split("/", 1)[0]
    host, _, port = raw.partition(":")
    return (host, int(port) if port.isdigit() else default_port)


def origin_for(value: str, default_port: int = 4939) -> str:
    host, port = split_host(value, default_port)
    if not host:
        raise ValueError("empty host")
    return f"http://{host}:{port}"


def reachable(origin: str, timeout: float = 1.5) -> bool:
    try:
        host, port = split_host(origin)
        with socket.create_connection((host, port), timeout):
            return True
    except OSError:
        return False


def choose_origin(hosts: Iterable[str], default_port: int = 4939) -> str:
    origins: List[str] = []
    for h in hosts:
        if not h:
            continue
        o = origin_for(h, default_port)
        if o not in origins:
            origins.append(o)
    if not origins:
        raise ValueError("no hosts")
    for o in origins:
        if reachable(o):
            return o
    return origins[0]


def _ssh(ssh_target: str, snippet: str, timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", f"ConnectTimeout={timeout}",
         "-o", "StrictHostKeyChecking=accept-new", ssh_target, snippet],
        capture_output=True, text=True, timeout=timeout + 15,
    )


def local_ports(ssh_target: str, timeout: int = 15) -> List[int]:
    """Ports of mirasim servers running on the host, from ~/.mirasim/run."""
    proc = _ssh(ssh_target, 'ls "$HOME"/.mirasim/run/local-*.token 2>/dev/null', timeout)
    ports = []
    for line in (proc.stdout or "").splitlines():
        name = line.rsplit("/", 1)[-1]
        if name.startswith("local-") and name.endswith(".token"):
            value = name[len("local-"):-len(".token")]
            if value.isdigit():
                ports.append(int(value))
    return ports


def _fetch_once(ssh_target: str, port: int, timeout: int) -> dict:
    snippet = (
        f'T=$(cat "$HOME/.mirasim/run/local-{port}.token" 2>/dev/null)\n'
        f'[ -n "$T" ] || exit 3\n'
        f'curl -fsS "http://127.0.0.1:{port}/mirachannel/pair?token=$T"'
    )
    proc = _ssh(ssh_target, snippet, timeout)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip()[:300] or "ssh failed")
    pair = json.loads(proc.stdout)
    if not pair.get("ok"):
        raise RuntimeError("pair endpoint refused: %s" % (pair.get("error") or pair))
    return pair


def host_patch_status(ssh_target: str, timeout: int = 15) -> dict:
    """Check the optional host g2/role verifier markers in server-main.cjs."""
    if not ssh_target:
        return {}
    snippet = (
        'python3 - <<"PY"\n'
        'import json,os\n'
        'p="/Applications/Mirasim.app/Contents/Resources/server-main.cjs"\n'
        'try:\n'
        ' s=open(p,encoding="utf-8",errors="replace").read()\n'
        ' print(json.dumps({"g2":"mld-g2-auth" in s,"role":"mld-member-role" in s}))\n'
        'except Exception as e:\n'
        ' print(json.dumps({"error":str(e)}))\n'
        'PY'
    )
    proc = _ssh(ssh_target, snippet, timeout)
    try:
        return json.loads(proc.stdout.strip() or "{}")
    except ValueError:
        return {"error": (proc.stderr or proc.stdout).strip()[:200]}


def shared_accounts(ssh_target: str, timeout: int = 15) -> List[str]:
    """Read the host's mirachannelSharedAccounts setting (member account ids)."""
    if not ssh_target:
        return []
    snippet = (
        'python3 - <<"PY"\n'
        'import json,os\n'
        'p=os.path.expanduser("~/.mirasim/setting.json")\n'
        'd=json.load(open(p))\n'
        'v=d.get("mirachannelSharedAccounts") or []\n'
        'print(json.dumps(v if isinstance(v,list) else []))\n'
        'PY'
    )
    proc = _ssh(ssh_target, snippet, timeout)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip()[:300] or "ssh failed")
    try:
        return json.loads(proc.stdout.strip() or "[]")
    except ValueError:
        return []


def fetch_pair(ssh_target: str, port: Optional[int] = None, timeout: int = 20) -> Tuple[dict, int]:
    """Read /mirachannel/pair from the host, discovering the server port.

    The host may restart on a different port (the desktop app uses 4970 by
    default, a manual ``serve`` may use another). Try the configured port first,
    then every ``local-<port>.token`` on the host. Returns ``(pair, port)``.
    """
    if not ssh_target:
        raise ValueError("no ssh target configured")
    ports: List[int] = []
    if port:
        ports.append(int(port))
    try:
        for p in local_ports(ssh_target, timeout):
            if p not in ports:
                ports.append(p)
    except Exception:
        pass
    if not ports:
        ports = [4939]
    errors = []
    for p in ports:
        try:
            return _fetch_once(ssh_target, p, timeout), p
        except Exception as exc:
            errors.append("%s: %s" % (p, exc))
    raise RuntimeError("could not read the host pair endpoint (" + "; ".join(errors) + ")")
