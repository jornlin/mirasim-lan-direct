"""App discovery, backups, locking, process control, logging."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import config


def asar_version(path: Path) -> str:
    """Read the app version from package.json inside an asar."""
    try:
        with Path(path).open("rb") as fh:
            import struct
            head = fh.read(16)
            if len(head) < 16 or struct.unpack("<I", head[0:4])[0] != 4:
                return "unknown"
            header_size = struct.unpack("<I", head[4:8])[0]
            json_len = struct.unpack("<I", head[12:16])[0]
            fh.seek(16)
            tree = json.loads(fh.read(json_len))
            data_start = 8 + header_size
            def walk(node, prefix=""):
                for name, value in node.items():
                    full = prefix + "/" + name
                    if "files" in value:
                        yield from walk(value["files"], full)
                    else:
                        yield full, value
            entry = dict(walk(tree["files"])).get("/package.json")
            if entry:
                fh.seek(data_start + int(entry["offset"]))
                pkg = json.loads(fh.read(int(entry["size"])))
                if pkg.get("version"):
                    return str(pkg["version"])
    except Exception:
        pass
    return "unknown"


@dataclass
class App:
    root: Path
    asar: Path
    binary: Path

    @property
    def version(self) -> str:
        return asar_version(self.asar)


def app_candidates() -> list[Path]:
    home = Path.home()
    if sys.platform == "darwin":
        return [Path("/Applications/Mirasim.app"), home / "Applications" / "Mirasim.app"]
    if sys.platform == "win32":
        out = []
        local = os.environ.get("LOCALAPPDATA")
        pf = os.environ.get("ProgramFiles")
        pf86 = os.environ.get("ProgramFiles(x86)")
        if local:
            out += [Path(local) / "Programs" / "Mirasim", Path(local) / "Mirasim"]
        if pf:
            out.append(Path(pf) / "Mirasim")
        if pf86:
            out.append(Path(pf86) / "Mirasim")
        return out
    return []


def find_app(explicit: Optional[str] = None) -> App:
    roots = [Path(explicit).expanduser()] if explicit else app_candidates()
    for root in roots:
        if sys.platform == "darwin":
            asar = root / "Contents" / "Resources" / "app.asar"
            binary = root / "Contents" / "MacOS" / "Mirasim"
        else:
            asar = root / "resources" / "app.asar"
            binary = root / "Mirasim.exe"
        if asar.is_file():
            return App(root=root, asar=asar, binary=binary)
    raise FileNotFoundError(
        "Mirasim app not found; pass --app <path> (looked in: %s)" %
        ", ".join(str(r) for r in roots)
    )


def _darwin_main_running(binary: str, ps_output: Optional[str] = None) -> bool:
    """Whether the GUI main process is alive.

    Mirasim also starts ``server.cjs``, ``cli.cjs`` and ``screen-lane.cjs``
    from the same executable. ``pgrep -f <binary>`` matches those helpers, so
    a quit looks failed and a patch looks unsafe long after the window is
    gone. The Electron main process is the one whose command line is exactly
    the bundle binary, with no script argument.
    """
    if ps_output is None:
        r = subprocess.run(["ps", "-axo", "command="], capture_output=True, text=True)
        ps_output = r.stdout or ""
    return any(line.strip() == binary for line in ps_output.splitlines())


def is_running(app: App) -> bool:
    if sys.platform == "darwin":
        return _darwin_main_running(str(app.binary))
    if sys.platform == "win32":
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Mirasim.exe"],
                           capture_output=True, text=True)
        return "Mirasim.exe" in (r.stdout or "")
    r = subprocess.run(["pgrep", "-f", str(app.binary)], capture_output=True)
    return r.returncode == 0


def quit_app(app: App, wait: float = 15.0) -> bool:
    if sys.platform == "darwin":
        subprocess.run(["osascript", "-e", 'tell application "Mirasim" to quit'],
                       capture_output=True)
    elif sys.platform == "win32":
        subprocess.run(["taskkill", "/IM", "Mirasim.exe"], capture_output=True)
    else:
        subprocess.run(["pkill", "-f", str(app.binary)], capture_output=True)
    deadline = time.time() + wait
    while time.time() < deadline:
        if not is_running(app):
            return True
        time.sleep(0.5)
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/F", "/IM", "Mirasim.exe"], capture_output=True)
        time.sleep(1)
        return not is_running(app)
    return not is_running(app)


def launch(app: App) -> None:
    if sys.platform == "darwin":
        subprocess.run(["open", "-a", str(app.root)], check=False)
    else:
        subprocess.Popen([str(app.binary)], cwd=str(app.root))


def install(app: App, data: bytes) -> None:
    tmp = app.asar.with_name(app.asar.name + ".new")
    tmp.write_bytes(data)
    if os.name == "posix":
        os.chmod(tmp, 0o600)
    os.replace(tmp, app.asar)


def backup(app: App, version: str) -> Path:
    d = config.backups_dir()
    d.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    dest = d / f"app.asar.{version}.{stamp}"
    shutil.copy2(app.asar, dest)
    (dest.with_name(dest.name + ".version")).write_text(version + "\n", encoding="utf-8")
    return dest


def pristine_candidates(version: str) -> list[Path]:
    out: list[Path] = []
    candidates = []
    original = config.config_dir() / "app.asar.orig"
    if original.is_file():
        candidates.append(original)
    d = config.backups_dir()
    if d.is_dir():
        candidates += [p for p in sorted(d.glob("app.asar.*"),
                                         key=lambda x: x.stat().st_mtime, reverse=True)
                       if not p.name.endswith(".version")]
    for path in candidates:
        if asar_version(path) == version:
            out.append(path)
    return out


@contextmanager
def lock(timeout: int = 900):
    path = config.lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            age = time.time() - path.stat().st_mtime
        except OSError:
            age = timeout + 1
        if age > timeout:
            try:
                path.unlink()
            except OSError:
                pass
        else:
            yield False
            return
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        yield False
        return
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield True
    finally:
        try:
            path.unlink()
        except OSError:
            pass


def log(message: str) -> None:
    config.config_dir().mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with config.log_path().open("a", encoding="utf-8") as fh:
        fh.write(f"{stamp} {message}\n")