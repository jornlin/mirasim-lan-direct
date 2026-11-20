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


def fetch_pair(ssh_target: str, port: int = 4939, timeout: int = 20) -> dict:
    """Read /mirachannel/pair from the host's loopback over SSH.

    The endpoint is loopback-only by design; SSH is the supported way in.
    """
    if not ssh_target:
        raise ValueError("no ssh target configured")
    snippet = (
        f'T=$(cat "$HOME/.mirasim/run/local-{port}.token" 2>/dev/null)\n'
        f'[ -n "$T" ] || T=$(cat "$(ls "$HOME"/.mirasim/run/local-*.token 2>/dev/null | head -1)" 2>/dev/null)\n'
        f'[ -n "$T" ] || exit 3\n'
        f'curl -fsS "http://127.0.0.1:{port}/mirachannel/pair?token=$T"'
    )
    proc = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", f"ConnectTimeout={timeout}",
         "-o", "StrictHostKeyChecking=accept-new", ssh_target, snippet],
        capture_output=True, text=True, timeout=timeout + 15,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip()[:400] or "ssh failed")
    pair = json.loads(proc.stdout)
    if not pair.get("ok"):
        raise RuntimeError("pair endpoint refused: %s" % (pair.get("error") or pair))
    return pair