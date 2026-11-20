"""The renderer patch: route selected cloud spaces over the LAN.

Two independent changes are made inside the app's ``app.asar``:

1. The function that builds a cloud-space transport target is rewritten so that
   the configured cloud node ids get ``host`` / ``token`` / ``e2e`` injected and
   lose ``gatewayUrl`` / ``grant``. The decorator then picks mirachannel's LAN
   WebSocket route instead of the gateway socket.
2. The renderer's Content-Security-Policy is widened to allow the LAN origins
   (otherwise the browser blocks the WebSocket and the app falls back to relay).

The function is found by its shape, never by the hashed asset name, so the tool
keeps working across app versions. If the shape is missing, nothing is written.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Sequence

from .asar import Asar

MARK_PREFIX = "mirasim-lan-direct:"
PATCH_REVISION = 2   # bump when the set of rewrite points changes
LEGACY_MARKERS = ("mirasim-lan-patch:", "mirasim-lan-patch")

# function <name>(<param>){const <var>=<param>.gatewayUrl??"";return{mode:"remote",host:""
L_RE = re.compile(
    rb'function ([A-Za-z_$][\w$]*)\(([A-Za-z_$][\w$]*)\)\{const ([A-Za-z_$][\w$]*)='
    rb'\2\.gatewayUrl\?\?"";return\{mode:"remote",host:""'
)


class PatchError(RuntimeError):
    pass


@dataclass(frozen=True)
class Target:
    node_id: str
    origin: str          # http://host:port
    token: str
    e2e: str             # host E2E public key
    install_id: str = ""  # stable client id, so the host supersedes the previous device row
    collab: bool = False  # enable the collab presence gate for this direct target

    def as_config(self) -> dict:
        cfg = {"o": self.origin, "t": self.token, "k": self.e2e}
        if self.install_id:
            cfg["i"] = self.install_id
        if self.collab:
            cfg["c"] = 1
        return cfg


@dataclass
class PatchResult:
    changed: List[str] = field(default_factory=list)
    origins: List[str] = field(default_factory=list)
    marker: str = ""


def target_hash(targets: Sequence[Target]) -> str:
    canonical = json.dumps(
        {"rev": PATCH_REVISION,
         "targets": sorted((t.node_id, t.origin, t.token, t.e2e, t.install_id, t.collab)
                           for t in targets)},
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:12]


def marker_for(targets: Sequence[Target]) -> str:
    return f"/*{MARK_PREFIX}{target_hash(targets)}*/"


def read_marker(asar: Asar) -> str:
    for path, data in asar.contents.items():
        if not path.endswith((".js", ".mjs")):
            continue
        i = data.find(MARK_PREFIX.encode())
        if i >= 0:
            start = data.rfind(b"/*", 0, i)
            end = data.find(b"*/", i)
            if start >= 0 and end >= 0:
                return data[start:end + 2].decode("utf-8", "replace")
        for legacy in LEGACY_MARKERS:
            j = data.find(legacy.encode())
            if j >= 0:
                return data[max(0, j - 2):j + 64].decode("utf-8", "replace")
    return ""


PATCHED_SIGNATURE = re.compile(rb'nodeId==="[^"]+";return\{mode:"remote",host:')


def looks_patched(asar: Asar, origins: Iterable[str] = ()) -> bool:
    marker = read_marker(asar)
    if marker:
        return True
    blob = b"".join(asar.contents.values())
    if any(o.encode() in blob for o in origins):
        return True
    # Older builds of this tool had no marker; detect the rewritten function
    # independently of the address, so a changed host/port still counts.
    return bool(PATCHED_SIGNATURE.search(blob))


def _find_function(asar: Asar):
    hits = []
    for path, data in asar.contents.items():
        if not path.endswith((".js", ".mjs")):
            continue
        for m in L_RE.finditer(data):
            hits.append((path, m))
    if len(hits) != 1:
        raise PatchError(
            "expected exactly one cloud-target function, found %d "
            "(the app version may already be patched or use a different build)" % len(hits)
        )
    return hits[0]


def _function_end(data: bytes, start: int) -> int:
    brace = data.find(b"{", start)
    if brace < 0:
        raise PatchError("malformed target function")
    depth = 0
    for i in range(brace, len(data)):
        c = data[i:i + 1]
        if c == b"{":
            depth += 1
        elif c == b"}":
            depth -= 1
            if depth == 0:
                return i + 1
    raise PatchError("unbalanced braces in target function")


def _helper_names(span: bytes, param: str) -> tuple:
    """Extract the minified names the original function calls, so the rewrite
    keeps working when the bundler renames them."""
    p = re.escape(param.encode())
    grant = re.search(rb'\.\.\.([A-Za-z_$][\w$]*)\(' + p + rb'\)&&!' + p + rb'\.token', span)
    v2 = re.search(rb'\.\.\.([A-Za-z_$][\w$]*)\(' + p + rb'\)\}\}$', span)
    rend = re.search(rb'rendezvous:' + p + rb'\.rendezvous\|\|([A-Za-z_$][\w$]*)', span)
    if not (grant and v2 and rend):
        raise PatchError("could not identify the helper functions in the target function")
    return (grant.group(1).decode(), v2.group(1).decode(), rend.group(1).decode())


def _new_function(name: str, param: str, targets: Sequence[Target],
                  grant_fn: str, v2_fn: str, rend: str) -> bytes:
    table = json.dumps(
        {t.node_id: t.as_config() for t in targets},
        separators=(",", ":"),
        ensure_ascii=True,
        sort_keys=True,
    )
    tbl = "Q" if param != "Q" else "R"
    ent = "d" if param != "d" else "u"
    code = (
        f'function {name}({param}){{const {tbl}={table};const {ent}={tbl}[{param}.nodeId];'
        f'if({ent}&&{ent}.c)globalThis.__mldCollab=true;'
        f'return{{mode:"remote",host:{ent}?{ent}.o:({param}.host??""),'
        f'token:{ent}?{ent}.t:({param}.token??""),'
        f'...{ent}?{{}}:{grant_fn}({param})&&!{param}.token?{{grant:{param}.grant}}:{{}},'
        f'...{param}.grantAt>=0?{{grantAt:{param}.grantAt}}:{{}},'
        f'...!{ent}&&{param}.gatewayUrl?{{gatewayUrl:{param}.gatewayUrl}}:{{}},'
        f'nodeId:{param}.nodeId,e2e:{ent}?{ent}.k:{param}.e2e,'
        f'installId:{ent}?{ent}.i:({param}.installId??""),'
        f'rendezvous:{param}.rendezvous||{rend},...{v2_fn}({param})'
    ).encode() + b'}}' + marker_for(targets).encode()
    return code


def patch_js(asar: Asar, targets: Sequence[Target]) -> List[str]:
    path, match = _find_function(asar)
    data = asar.contents[path]
    start = match.start()
    end = _function_end(data, start)
    name = match.group(1).decode()
    param = match.group(2).decode()
    grant_fn, v2_fn, rend = _helper_names(data[start:end], param)
    asar.contents[path] = (data[:start]
                           + _new_function(name, param, targets, grant_fn, v2_fn, rend)
                           + data[end:])
    return [path]


E_RE = re.compile(
    rb'function ([A-Za-z_$][\w$]*)\(([A-Za-z_$][\w$]*)\)\{return \2\.mode!=="remote"\?null:'
    rb'\{mode:"remote",host:'
)


def patch_install_id(asar: Asar) -> List[str]:
    """Make the final target builder pass installId through.

    The cloud window path rebuilds the target in a second helper; without this,
    the v2 client never sends a stable installId and the host stores a new
    legacy device on every connection.
    """
    hits = []
    for path, data in asar.contents.items():
        if not path.endswith((".js", ".mjs")):
            continue
        for m in E_RE.finditer(data):
            hits.append((path, m))
    if len(hits) != 1:
        raise PatchError("expected exactly one target pass-through function, found %d" % len(hits))
    path, m = hits[0]
    data = asar.contents[path]
    start = m.start()
    end = _function_end(data, start)
    param = m.group(2).decode()
    span = data[start:end]
    needle = ("nodeId:%s.nodeId||void 0," % param).encode()
    if span.count(needle) != 1:
        raise PatchError("could not find the nodeId field in the target pass-through function")
    span = span.replace(needle, needle + ("installId:%s.installId||void 0," % param).encode())
    asar.contents[path] = data[:start] + span + data[end:]
    return [path]


ROUTE_RE = re.compile(
    rb'client:([A-Za-z_$][\w$]*)\(\{host:([A-Za-z_$][\w$]*)\.host,hosts:\2\.hosts,'
    rb'rendezvous:\2\.rendezvous,nodeId:\2\.nodeId,token:\2\.token,grant:\2\.grant,e2e:\2\.e2e,'
)


def patch_install_id_route(asar: Asar) -> List[str]:
    """Pass installId into the mirachannel client options.

    The transport dispatcher builds the switchable-client options field by
    field; without this insertion the target's installId never reaches the v2
    HELLO, and the host stores a new device on every connection.
    """
    hits = []
    for path, data in asar.contents.items():
        if not path.endswith((".js", ".mjs")):
            continue
        for m in ROUTE_RE.finditer(data):
            hits.append((path, m))
    if len(hits) != 1:
        raise PatchError("expected exactly one mirachannel route builder, found %d" % len(hits))
    path, m = hits[0]
    data = asar.contents[path]
    start, end = m.start(), m.end()
    param = m.group(2).decode()
    insert = ("...%s.installId?{installId:%s.installId}:{}," % (param, param)).encode()
    asar.contents[path] = data[:end] + insert + data[end:]
    return [path]


COLLAB_GATE_RE = re.compile(rb'\.state\.collab===!0')


def patch_collab_gate(asar: Asar) -> List[str]:
    """Let a direct window enable the collab presence gate.

    The renderer turns presence on only when the host's state frame says
    ``collab: true``. The host's presence service itself is gated by the space's
    cloud-attach state, so a direct connection can participate; this makes the
    client gate robust when the state flag is missing or arrives late.
    """
    hits = []
    for path, data in asar.contents.items():
        if not path.endswith((".js", ".mjs")):
            continue
        for m in COLLAB_GATE_RE.finditer(data):
            hits.append((path, m))
    if len(hits) != 1:
        raise PatchError("expected exactly one collab presence gate, found %d" % len(hits))
    path, m = hits[0]
    data = asar.contents[path]
    insert = b".state.collab===!0||globalThis.__mldCollab===!0"
    asar.contents[path] = data[:m.start()] + insert + data[m.end():]
    return [path]


def _csp_host(origin: str) -> str:
    return origin.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]


def patch_csp(asar: Asar, origins: Sequence[str]) -> List[str]:
    hosts = sorted({_csp_host(o) for o in origins})
    if not hosts:
        return []
    changed = []
    for path, data in list(asar.contents.items()):
        if not path.endswith("/renderer/index.html"):
            continue
        html = data.decode("utf-8")
        if "Content-Security-Policy" not in html:
            raise PatchError("renderer index.html has no Content-Security-Policy")
        before = html
        for directive in ("connect-src", "img-src", "media-src", "object-src", "frame-src"):
            pattern = re.compile(r"(" + directive + r"[^;]*?)(;|\")")

            def add(m, directive=directive):
                body, tail = m.group(1), m.group(2)
                extra = " " + " ".join(
                    f"http://{h}:* ws://{h}:*" if directive == "connect-src" else f"http://{h}:*"
                    for h in hosts
                )
                if extra.strip() in body:
                    return m.group(0)
                return body + extra + tail

            html = pattern.sub(add, html, count=1)
        if "</html>" not in html:
            raise PatchError("patched renderer index.html looks truncated")
        if html != before:
            asar.contents[path] = html.encode("utf-8")
            changed.append(path)
    return changed


def _node_binary(app_binary: str | Path | None, asar_path: str | Path | None) -> Path | None:
    if app_binary:
        p = Path(app_binary)
        return p if p.is_file() else None
    if not asar_path:
        return None
    p = Path(asar_path).resolve()
    for candidate in (
        p.parent.parent / "MacOS" / "Mirasim",
        p.parent.parent / "Mirasim.exe",
        p.parent.parent.parent / "Mirasim.exe",
    ):
        if candidate.is_file():
            return candidate
    return None


def validate_js(binary: Path, data: bytes, label: str) -> None:
    fd, tmp = tempfile.mkstemp(suffix=".mjs")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        env = dict(os.environ, ELECTRON_RUN_AS_NODE="1")
        proc = subprocess.run([str(binary), "--check", tmp],
                              env=env, capture_output=True, text=True, timeout=90)
        if proc.returncode != 0:
            raise PatchError(
                "syntax check failed for %s: %s" %
                (label, (proc.stderr or proc.stdout).strip()[:600])
            )
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def apply(asar: Asar, targets: Sequence[Target], *, app_binary: str | Path | None = None,
          node_binary: str | Path | None = None, validate: bool = True) -> PatchResult:
    changed = patch_js(asar, targets)
    changed += patch_install_id(asar)
    changed += patch_install_id_route(asar)
    changed += patch_collab_gate(asar)
    origins = [t.origin for t in targets]
    changed += patch_csp(asar, origins)
    if validate:
        binary = _node_binary(node_binary or app_binary, None)
        if binary is None:
            raise PatchError("cannot find the app's Electron binary for syntax checking; "
                             "pass --node")
        for path in changed:
            if path.endswith((".js", ".mjs")):
                validate_js(binary, asar.contents[path], path)
    return PatchResult(changed=list(dict.fromkeys(changed)), origins=origins,
                       marker=marker_for(targets))