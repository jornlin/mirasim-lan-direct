"""Runtime configuration and state.

Code lives in the repository; configuration (which contains a host's access
token) lives outside it, in the OS application-support directory, mode 0600.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional



APP_NAME = "mirasim-lan-direct"


def config_dir() -> Path:
    override = os.environ.get("MLD_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_NAME
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / APP_NAME


def config_path() -> Path:
    return config_dir() / "config.json"


def backups_dir() -> Path:
    return config_dir() / "backups"


def log_path() -> Path:
    return config_dir() / "autopatch.log"


def lock_path() -> Path:
    return config_dir() / ".lock"


def disabled_path() -> Path:
    return config_dir() / "DISABLED"


DEFAULT_CONFIG: dict = {
    "version": 1,
    "app": "",
    "targets": [],
    "ssh": {"target": "", "port": 4939},
    "autoPatch": {"intervalSeconds": 300, "pairRefreshHours": 6},
}


def load() -> dict:
    path = config_path()
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        cfg = json.load(fh)
    if not isinstance(cfg, dict):
        raise ValueError("config.json must be an object")
    return cfg


def save(cfg: dict) -> Path:
    d = config_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = config_path()
    fd, tmp = tempfile.mkstemp(dir=str(d), prefix=".config.", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    return path


def entry_from_pair(pair: dict, hosts_override: Optional[List[str]] = None) -> dict:
    """Turn a /mirachannel/pair response into a config target entry."""
    cloud = pair.get("cloudAttach") or {}
    node_id = cloud.get("nodeId") or pair.get("nodeId")
    if not node_id:
        raise ValueError("pair data has no cloud node id (cloudAttach.nodeId)")
    if not pair.get("token") or not pair.get("e2e"):
        raise ValueError("pair data has no token/e2e")
    hosts = hosts_override if hosts_override else (pair.get("hosts") or [])
    if not hosts:
        raise ValueError("pair data has no hosts")
    return {
        "nodeId": node_id,
        "label": pair.get("machine") or node_id,
        "hosts": hosts,
        "token": pair["token"],
        "e2e": pair["e2e"],
    }


# Fields that describe the user's choice for a target, not the host. The pair
# endpoint cannot supply them, so a refresh must carry them over from the old
# entry; otherwise a periodic pair refresh silently resets `mode`/`collab`
# (and member grants) back to a plain direct target.
PRESERVED_TARGET_FIELDS = ("label", "mode", "collab", "grant", "member", "installId")


def merge_pair_entry(old: dict, refreshed: dict) -> dict:
    """Merge fresh pair data into an existing target entry."""
    merged = dict(refreshed)
    for key in PRESERVED_TARGET_FIELDS:
        if old.get(key) not in (None, ""):
            merged[key] = old[key]
    merged["origin"] = ""
    return merged


def sanitized(cfg: dict) -> dict:
    """A copy safe to print: secrets replaced."""
    def mask(value: str) -> str:
        return value[:6] + "…" if isinstance(value, str) and len(value) > 6 else "***"
    out = json.loads(json.dumps(cfg))
    for entry in out.get("targets") or []:
        if "token" in entry:
            entry["token"] = mask(entry["token"])
        if "e2e" in entry:
            entry["e2e"] = mask(entry["e2e"])
    return out