"""Command line interface for mirasim-lan-direct."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from . import agent, asar as asar_mod, config, hostinfo, patch, system


# ---------------------------------------------------------------- helpers

def _load_cfg() -> dict:
    cfg = dict(config.DEFAULT_CONFIG)
    cfg.update(config.load())
    cfg.setdefault("targets", [])
    cfg.setdefault("ssh", {"target": "", "port": 4939})
    cfg.setdefault("autoPatch", {"intervalSeconds": 300, "pairRefreshHours": 6})
    return cfg


def _save_cfg(cfg: dict) -> None:
    config.save(cfg)


def _app(cfg: dict, explicit: Optional[str]) -> system.App:
    return system.find_app(explicit or cfg.get("app") or None)


def _ensure_install_ids(cfg: dict) -> bool:
    changed = False
    for entry in cfg.get("targets") or []:
        if (entry.get("mode") or "direct").lower() == "gateway":
            continue
        if not entry.get("installId"):
            entry["installId"] = "mld-" + uuid.uuid4().hex
            changed = True
    return changed


def _resolve_targets(cfg: dict) -> Tuple[List[patch.Target], bool]:
    default_port = int((cfg.get("ssh") or {}).get("port") or 4939)
    out: List[patch.Target] = []
    changed = False
    for entry in cfg.get("targets") or []:
        if (entry.get("mode") or "direct").lower() == "gateway":
            continue
        hosts = entry.get("hosts") or []
        origin = entry.get("origin")
        if not origin or not hostinfo.reachable(origin):
            try:
                origin = hostinfo.choose_origin(hosts or [origin], default_port)
            except ValueError:
                raise ValueError("target %s has no usable hosts" % entry.get("nodeId"))
            if entry.get("origin") != origin:
                entry["origin"] = origin
                changed = True
        out.append(patch.Target(entry["nodeId"], origin, entry["token"], entry["e2e"],
                               entry.get("installId") or ""))
    if not out and not (cfg.get("targets") or []):
        raise ValueError("no targets configured; run `mld init`")
    return out, changed


def _is_legacy_patch(asar: asar_mod.Asar) -> bool:
    marker = patch.read_marker(asar)
    return bool(marker) and marker.startswith("/*mirasim-lan-patch")


def _healthy(asar: asar_mod.Asar, targets: List[patch.Target]) -> bool:
    marker = patch.read_marker(asar)
    origins = [t.origin for t in targets]
    if marker == patch.marker_for(targets):
        return True
    if _is_legacy_patch(asar) or (not marker and patch.looks_patched(asar, origins)):
        return any(hostinfo.reachable(o) for o in origins)
    return False


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _refresh_pair(cfg: dict) -> bool:
    ssh = cfg.get("ssh") or {}
    target = (ssh.get("target") or "").strip()
    if not target:
        return False
    try:
        pair, detected = hostinfo.fetch_pair(target, int(ssh.get("port") or 0) or None)
        cfg.setdefault("ssh", {})["port"] = detected
        entry = config.entry_from_pair(pair)
    except Exception as exc:
        system.log("pair refresh failed: %s" % exc)
        return False
    entries = cfg.setdefault("targets", [])
    for i, old in enumerate(entries):
        if old.get("nodeId") == entry["nodeId"]:
            entry["origin"] = ""
            if old.get("installId"):
                entry["installId"] = old["installId"]
            entries[i] = entry
            break
    else:
        entries.append(entry)
    cfg["pairRefreshedAt"] = _timestamp()
    _save_cfg(cfg)
    system.log("pair refreshed for %s" % entry["nodeId"])
    return True


def _pair_is_stale(cfg: dict) -> bool:
    stamp = cfg.get("pairRefreshedAt")
    hours = float((cfg.get("autoPatch") or {}).get("pairRefreshHours") or 6)
    if not stamp:
        return True
    try:
        when = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return True
    return (datetime.now(timezone.utc) - when).total_seconds() > hours * 3600


def _choose_source(cfg: dict, app: system.App, current: asar_mod.Asar,
                   targets: List[patch.Target], original: Optional[str]) -> Tuple[asar_mod.Asar, bool]:
    origins = [t.origin for t in targets]
    if not patch.looks_patched(current, origins):
        return current, True
    candidates: List[Path] = []
    if original:
        cand = Path(original).expanduser()
        if system.asar_version(cand) != app.version:
            raise patch.PatchError(
                "--original is version %s but the installed app is %s" %
                (system.asar_version(cand), app.version))
        candidates.append(cand)
    candidates += system.pristine_candidates(app.version)
    for path in candidates:
        if not path.is_file():
            continue
        try:
            src = asar_mod.load(path)
        except Exception:
            continue
        if not patch.looks_patched(src, origins):
            return src, False
    raise patch.PatchError(
        "the installed app is already patched and no pristine app.asar for version "
        "%s was found; pass --original <unpatched app.asar> or reinstall the app" % app.version
    )


def _apply_and_install(cfg: dict, app: system.App, targets: List[patch.Target],
                       source: asar_mod.Asar, source_is_installed: bool,
                       *, restart: bool, dry_run: bool, log: bool) -> patch.PatchResult:
    result = patch.apply(source, targets, app_binary=app.binary)
    data = asar_mod.build(source)
    asar_mod.verify_bytes(data)

    if dry_run:
        return result

    running = system.is_running(app)
    if running and not restart:
        raise RuntimeError("Mirasim is running; close it first or pass --restart")
    if running and restart:
        if not system.quit_app(app):
            raise RuntimeError("Mirasim did not quit")
    if source_is_installed:
        system.backup(app, app.version)
    system.install(app, data)
    if log:
        system.log("patched %s (%s): %s" % (app.root, app.version, result.marker))
    if running and restart:
        system.launch(app)
    return result


# ---------------------------------------------------------------- commands

def cmd_init(args) -> int:
    cfg = _load_cfg()
    entry = None
    if args.pair:
        with open(args.pair, "r", encoding="utf-8") as fh:
            entry = config.entry_from_pair(json.load(fh), args.host or None)
    elif args.ssh:
        pair, detected = hostinfo.fetch_pair(args.ssh, args.port or None)
        entry = config.entry_from_pair(pair, args.host or None)
        cfg.setdefault("ssh", {})["port"] = detected
    elif args.token or args.e2e or args.node:
        if not (args.token and args.e2e and args.node and args.host):
            raise SystemExit("manual setup needs --token --e2e --node --host")
        entry = {
            "nodeId": args.node,
            "label": args.label or args.node,
            "hosts": args.host,
            "token": args.token,
            "e2e": args.e2e,
        }
    if entry:
        old = next((e for e in cfg.get("targets") or [] if e.get("nodeId") == entry["nodeId"]), None)
        if old and old.get("installId"):
            entry["installId"] = old["installId"]
        entries = [e for e in cfg.get("targets") or [] if e.get("nodeId") != entry["nodeId"]]
        entries.append(entry)
        cfg["targets"] = entries
    elif not cfg.get("targets"):
        raise SystemExit(
            "nothing to configure. Use one of:\n"
            "  mld init --ssh <host>                 # read the pair data over SSH\n"
            "  mld init --pair pair.json             # import a pair JSON file\n"
            "  mld init --node <id> --host <ip[:port]> --token <t> --e2e <k>\n"
        )
    _ensure_install_ids(cfg)
    if args.ssh:
        cfg["ssh"] = {"target": args.ssh, "port": (cfg.get("ssh") or {}).get("port") or args.port}
    if entry:
        cfg["pairRefreshedAt"] = _timestamp()
    if args.app:
        cfg["app"] = str(system.find_app(args.app).root)
    elif not cfg.get("app"):
        try:
            cfg["app"] = str(system.find_app().root)
        except FileNotFoundError:
            pass
    if args.original:
        src = Path(args.original).expanduser()
        try:
            app_ver = system.find_app(cfg.get("app") or None).version
        except Exception:
            app_ver = "unknown"
        if app_ver != "unknown" and system.asar_version(src) != app_ver:
            raise SystemExit("--original is version %s but the installed app is %s" %
                             (system.asar_version(src), app_ver))
        dst = config.config_dir() / "app.asar.orig"
        config.config_dir().mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        dst.with_name(dst.name + ".version").write_text(app_ver + "\n", encoding="utf-8")
    _save_cfg(cfg)
    print("config: %s" % config.config_path())
    print(json.dumps(config.sanitized(cfg), ensure_ascii=False, indent=2))
    print("\nnext: mld patch --restart   (or `mld agent install` for automatic re-patching)")
    return 0


def cmd_patch(args) -> int:
    try:
        config.disabled_path().unlink()
    except FileNotFoundError:
        pass
    cfg = _load_cfg()
    install_changed = _ensure_install_ids(cfg)
    app = _app(cfg, args.app)
    targets, changed = _resolve_targets(cfg)
    if changed or install_changed:
        _save_cfg(cfg)
    current = asar_mod.load(app.asar)
    if not targets:
        if not patch.looks_patched(current):
            print("no direct targets (all spaces are in gateway mode); nothing to patch")
            return 0
        if not args.force:
            print("all targets are in gateway mode; use --force to rebuild without direct routing")
            return 0
    if not args.force and targets and _healthy(current, targets):
        print("already patched for this configuration; nothing to do")
        return 0
    if not args.force and patch.looks_patched(current, [t.origin for t in targets]):
        print("an older patch is installed; use --force to rebuild it")
        return 0
    source, source_is_installed = _choose_source(cfg, app, current, targets, args.original)
    result = _apply_and_install(cfg, app, targets, source, source_is_installed,
                                restart=args.restart, dry_run=args.dry_run, log=False)
    if args.dry_run:
        print("dry run: would change %s, %d bytes" % (", ".join(result.changed), len(asar_mod.build(source))))
    else:
        print("patched %s (%s)" % (app.root, app.version))
        print("targets: " + ", ".join("%s -> %s" % (t.node_id, t.origin) for t in targets))
    return 0


def cmd_autopatch(args) -> int:
    if config.disabled_path().exists():
        return 0
    with system.lock() as acquired:
        if not acquired:
            return 0
        cfg = _load_cfg()
        if not cfg.get("targets"):
            system.log("autopatch: no targets configured")
            return 0
        try:
            install_changed = _ensure_install_ids(cfg)
            targets, changed = _resolve_targets(cfg)
            if changed or install_changed:
                _save_cfg(cfg)
            if _pair_is_stale(cfg) or not any(hostinfo.reachable(t.origin) for t in targets):
                _refresh_pair(cfg)
                install_changed = _ensure_install_ids(cfg)
                targets, changed = _resolve_targets(cfg)
                if changed or install_changed:
                    _save_cfg(cfg)
            app = _app(cfg, None)
            current = asar_mod.load(app.asar)
            if _healthy(current, targets):
                return 0
            if not any(hostinfo.reachable(t.origin) for t in targets):
                system.log("autopatch: no host reachable; keeping the current patch")
                return 0
            source, source_is_installed = _choose_source(cfg, app, current, targets, None)
            _apply_and_install(cfg, app, targets, source, source_is_installed,
                               restart=True, dry_run=False, log=True)
            return 0
        except Exception as exc:
            system.log("autopatch failed: %s" % exc)
            return 1


def cmd_check(args) -> int:
    cfg = _load_cfg()
    print("config:     %s" % config.config_path())
    print("platform:   %s" % sys.platform)

    try:
        targets, _ = _resolve_targets(cfg)
    except Exception as exc:
        print("targets:    %s" % exc)
        return 1

    current = None
    try:
        app = _app(cfg, args.app)
        print("app:        %s (%s)" % (app.root, app.version))
        current = asar_mod.load(app.asar)
        marker = patch.read_marker(current)
        origins = [t.origin for t in targets]
        if marker:
            print("installed:  %s" % marker)
        elif patch.looks_patched(current, origins):
            print("installed:  legacy patch (no marker)")
        else:
            print("installed:  not patched")
        print("running:    %s" % ("yes" if system.is_running(app) else "no"))
    except Exception as exc:
        print("app:        %s" % exc)

    want = patch.marker_for(targets)
    print("expected:   %s" % want)
    ok = True
    direct_nodes = {t.node_id for t in targets}
    for entry in cfg.get("targets") or []:
        if entry.get("nodeId") not in direct_nodes:
            print("target:     %s -> gateway/relay (collab mode)" % entry.get("nodeId"))
    for t in targets:
        up = hostinfo.reachable(t.origin)
        ok = ok and up
        print("target:     %s -> %s  %s" % (t.node_id, t.origin, "reachable" if up else "UNREACHABLE"))
    print("agent:      %s" % agent.status())

    if current is not None and _healthy(current, targets):
        marker = patch.read_marker(current)
        if marker == want:
            print("verdict:    patch current%s" %
                  ("; all targets reachable" if ok else "; WARNING: some targets unreachable"))
        else:
            print("verdict:    legacy patch is active; `mld patch --force --restart` upgrades it")
        return 0
    print("verdict:    rebuild needed (mld patch --restart)")
    return 1


def cmd_restore(args) -> int:
    config.disabled_path().parent.mkdir(parents=True, exist_ok=True)
    config.disabled_path().touch()
    cfg = _load_cfg()
    app = _app(cfg, args.app)
    candidates = []
    if args.original:
        cand = Path(args.original).expanduser()
        if system.asar_version(cand) != app.version:
            raise SystemExit("--original is version %s but the installed app is %s" %
                             (system.asar_version(cand), app.version))
        candidates.append(cand)
    candidates += system.pristine_candidates(app.version)
    if not candidates:
        raise SystemExit("no pristine app.asar for version %s; pass --original" % app.version)
    src = candidates[0]
    if system.is_running(app) and not system.quit_app(app):
        raise SystemExit("Mirasim did not quit")
    system.install(app, src.read_bytes())
    print("restored %s (version %s)" % (src, app.version))
    system.launch(app)
    return 0


def cmd_mode(args) -> int:
    cfg = _load_cfg()
    match = None
    for entry in cfg.get("targets") or []:
        if entry.get("nodeId") == args.target or entry.get("label") == args.target:
            match = entry
            break
    if match is None:
        raise SystemExit("no configured target matches %r" % args.target)
    match["mode"] = args.mode
    _save_cfg(cfg)
    print("%s is now %s" % (match.get("label") or match["nodeId"], args.mode))
    print("apply with: mld patch --force --restart")
    return 0


def cmd_agent(args) -> int:
    cfg = _load_cfg()
    if args.action == "status":
        print(agent.status())
        return 0
    if args.action == "uninstall":
        agent.uninstall()
        print("autopatch agent removed")
        return 0
    app = _app(cfg, args.app)
    interval = int((cfg.get("autoPatch") or {}).get("intervalSeconds") or 300)
    print("installed: %s" % agent.install(app.asar, interval))
    return 0


def cmd_doctor(args) -> int:
    print("python:     %s (%s)" % (sys.executable, sys.version.split()[0]))
    print("config dir: %s" % config.config_dir())
    print("config:     %s" % ("present" if config.config_path().exists() else "missing"))
    if config.config_path().exists():
        print("config mode:%s" % oct(config.config_path().stat().st_mode & 0o777))
    try:
        app = _app(_load_cfg(), args.app)
        print("app:        %s (%s)" % (app.root, app.version))
        print("asar:       %s bytes" % app.asar.stat().st_size)
        print("binary:     %s" % ("present" if app.binary.is_file() else "MISSING"))
        print("agent:      %s" % agent.status())
    except Exception as exc:
        print("app:        %s" % exc)
    return 0


# ---------------------------------------------------------------- parser

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mld",
        description="Route selected Mirasim cloud spaces over the LAN instead of the relay.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    i = sub.add_parser("init", help="write the runtime configuration")
    i.add_argument("--ssh", help="SSH target that can reach the host's loopback")
    i.add_argument("--port", type=int, default=0, help="host server port; 0 = auto-detect")
    i.add_argument("--pair", help="pair JSON file from /mirachannel/pair")
    i.add_argument("--host", action="append", help="LAN host[:port]; repeatable")
    i.add_argument("--token")
    i.add_argument("--e2e")
    i.add_argument("--node", help="cloud node id (cloudAttach.nodeId)")
    i.add_argument("--label")
    i.add_argument("--app", help="Mirasim.app / Mirasim install root")
    i.add_argument("--original", help="unpatched app.asar to keep for future rebuilds")
    i.set_defaults(func=cmd_init)

    pt = sub.add_parser("patch", help="build and install the renderer patch")
    pt.add_argument("--app")
    pt.add_argument("--force", action="store_true", help="rebuild even if already patched")
    pt.add_argument("--dry-run", action="store_true")
    pt.add_argument("--restart", action="store_true", help="quit and relaunch Mirasim")
    pt.add_argument("--original", help="unpatched app.asar to rebuild from")
    pt.set_defaults(func=cmd_patch)

    a = sub.add_parser("autopatch", help="agent entry: patch only when needed")
    a.set_defaults(func=cmd_autopatch)

    c = sub.add_parser("check", help="show whether direct routing is in use")
    c.add_argument("--app")
    c.set_defaults(func=cmd_check)

    r = sub.add_parser("restore", help="restore the original app.asar (disables autopatch)")
    r.add_argument("--app")
    r.add_argument("--original")
    r.set_defaults(func=cmd_restore)

    m = sub.add_parser("mode", help="choose direct LAN or gateway/relay (collaboration) for a space")
    m.add_argument("target", help="node id or label")
    m.add_argument("mode", choices=["direct", "gateway"])
    m.set_defaults(func=cmd_mode)

    ag = sub.add_parser("agent", help="install/remove the background re-patcher")
    ag.add_argument("action", choices=["install", "uninstall", "status"])
    ag.add_argument("--app")
    ag.set_defaults(func=cmd_agent)

    d = sub.add_parser("doctor", help="diagnose paths, permissions and agent state")
    d.add_argument("--app")
    d.set_defaults(func=cmd_doctor)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except (patch.PatchError, FileNotFoundError, ValueError, RuntimeError, OSError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1