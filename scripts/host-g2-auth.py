#!/usr/bin/env python3
"""Accept a Mirasim g2 gateway session as a direct LAN account grant.

Mirasim's desktop cloud flow hands each signed-in user a short-lived g2
gateway session for an attached machine (claims: sub = account, aud = cloud
node id, kind = gateway). The host normally accepts only g1 enroll grants on
its direct mirachannel listener. This patch adds a g2 verifier in the host's
``Flo`` enrollment branch, using the g2 public key that ships with the host.

Run it on the host machine (the computer that owns the space):

    python3 host-g2-auth.py --apply
    python3 host-g2-auth.py --restore
    python3 host-g2-auth.py --check

--apply creates a timestamped backup next to server-main.cjs. The first
successful direct connection enrolls a normal ``via=account`` device; later
reconnects use the device keys and do not need the short-lived session again.
An app update replaces server-main.cjs, so re-apply after updating Mirasim.

Only the g2 signature, ``kind``, ``aud`` and expiry are checked. A valid
session for another node is rejected. Revoke a member by revoking their
account device / account access as usual.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

G2_PUB = "MCowBQYDK2VwAyEAOmNXkUzCeX8EnTNFifxbOldQTJHuERtnLIsB1qmOiu8"
MARKER = "/*mld-g2-auth*/"
OLD = 'if(g5["grant"]){if(!a4["grants"])'
INJECT = (
    'if(g5["grant"]){'
    + MARKER
    + 'try{let _g=g5["grant"],_i=_g.indexOf("."),_c=require("node:crypto"),'
    '_k=_c.createPublicKey({key:Buffer.from("' + G2_PUB + '","base64url"),format:"der",type:"spki"}),'
    '_ok=_i>0&&_c.verify(null,Buffer.from(_g.slice(0,_i)),_k,Buffer.from(_g.slice(_i+1),"base64url")),'
    '_m=_ok?JSON.parse(Buffer.from(_g.slice(0,_i),"base64url").toString()):null,'
    '_n=(ye()?.["cloudAttachState"]?.["nodeId"])||'
    '(typeof a4["grants"]["opts"]["nodeId"]==="function"?a4["grants"]["opts"]["nodeId"]():a4["grants"]["opts"]["nodeId"]);'
    'if(_m&&_m["kind"]==="gateway"&&_m["aud"]===_n&&_m["sub"]&&_m["exp"]>Math.floor(Date.now()/1000))'
    'return{ok:!0,name:_m["name"]??g5["name"],via:"account",accountId:_m["sub"],'
    'role:_m["role"]==="member"?"member":"admin",'
    '...Rs(_m["email"])?{accountLabel:Rs(_m["email"])}:{}}}catch{}'
    'if(!a4["grants"])'
)


def default_file() -> Path:
    return Path("/Applications/Mirasim.app/Contents/Resources/server-main.cjs")


def backup_for(path: Path) -> Path:
    return path.with_name(path.name + ".mld-bak")


def check(path: Path) -> int:
    app = path.parent.parent / "MacOS" / "Mirasim"
    if not app.is_file():
        fallback = Path("/Applications/Mirasim.app/Contents/MacOS/Mirasim")
        if not fallback.is_file():
            print("cannot find the Electron binary next to", path, file=sys.stderr)
            return 2
        app = fallback
    env = dict(os.environ, ELECTRON_RUN_AS_NODE="1")
    proc = subprocess.run([str(app), "--check", str(path)], env=env,
                          capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        print((proc.stderr or proc.stdout).strip()[:800], file=sys.stderr)
        return proc.returncode
    print("syntax ok")
    return 0


def apply(path: Path) -> int:
    text = path.read_text(encoding="utf-8", errors="surrogateescape")
    if MARKER in text:
        print("already patched")
        return 0
    if text.count(OLD) != 1:
        print("expected one Flo enrollment branch, found", text.count(OLD), file=sys.stderr)
        return 2
    backup = backup_for(path)
    shutil.copy2(path, backup)
    path.write_text(text.replace(OLD, INJECT, 1), encoding="utf-8", errors="surrogateescape")
    print("patched", path, "backup", backup)
    return check(path)


def restore(path: Path) -> int:
    backup = backup_for(path)
    if not backup.is_file():
        print("no backup at", backup, file=sys.stderr)
        return 2
    shutil.copy2(backup, path)
    print("restored", path, "from", backup)
    return check(path)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=str(default_file()))
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--apply", action="store_true")
    g.add_argument("--restore", action="store_true")
    g.add_argument("--check", action="store_true")
    args = ap.parse_args()
    path = Path(args.file)
    if not path.is_file():
        print("not found:", path, file=sys.stderr)
        return 2
    if args.apply:
        return apply(path)
    if args.restore:
        return restore(path)
    return check(path)


if __name__ == "__main__":
    raise SystemExit(main())
