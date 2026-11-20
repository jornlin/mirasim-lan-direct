"""Install the background re-patcher (LaunchAgent on macOS, Scheduled Task on Windows)."""

from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path
from . import config

LABEL = "io.github.mirasim-lan-direct.autopatch"
WIN_TASK = "Mirasim LAN Direct"
WIN_TASK_LOGON = "Mirasim LAN Direct (logon)"


def _python() -> str:
    # Prefer the system Python so the LaunchAgent survives venv/uv changes.
    if sys.platform == "darwin" and Path("/usr/bin/python3").exists():
        return "/usr/bin/python3"
    return sys.executable or "python3"


def _runtime_dir() -> Path:
    """Copy the package next to the config so launchd/Task Scheduler does not
    need to read the repository (which may live under a TCC-protected folder
    such as ~/Documents or ~/Downloads)."""
    src = Path(__file__).resolve().parent
    dst = config.config_dir() / "runtime" / "mld"
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        if item.name == "__pycache__":
            continue
        target = dst / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)
    return dst.parent


def _env() -> dict:
    env = {"PYTHONPATH": str(_runtime_dir())}
    if os.environ.get("MLD_CONFIG_DIR"):
        env["MLD_CONFIG_DIR"] = os.environ["MLD_CONFIG_DIR"]
    return env


def macos_install(asar_path: Path, interval: int) -> Path:
    plist_path = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    log = config.log_path()
    payload = {
        "Label": LABEL,
        "ProgramArguments": [_python(), "-m", "mld", "autopatch"],
        "EnvironmentVariables": _env(),
        "RunAtLoad": True,
        "StartInterval": max(60, int(interval)),
        "WatchPaths": [str(asar_path)],
        "StandardOutPath": str(log),
        "StandardErrorPath": str(log),
        "ProcessType": "Background",
        "LowPriorityIO": True,
    }
    with plist_path.open("wb") as fh:
        plistlib.dump(payload, fh)
    uid = os.getuid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}/{LABEL}"], capture_output=True)
    r = subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(plist_path)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("launchctl bootstrap failed: " + (r.stderr or r.stdout).strip())
    subprocess.run(["launchctl", "enable", f"gui/{uid}/{LABEL}"], capture_output=True)
    return plist_path


def macos_uninstall() -> None:
    plist_path = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"], capture_output=True)
    try:
        plist_path.unlink()
    except FileNotFoundError:
        pass


def macos_status() -> str:
    r = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
    for line in (r.stdout or "").splitlines():
        if LABEL in line:
            return line.strip()
    return "not loaded"


def windows_install(interval: int) -> Path:
    d = config.config_dir()
    d.mkdir(parents=True, exist_ok=True)
    cmd = d / "autopatch.cmd"
    py = _python()
    src = str(_runtime_dir())
    log = config.log_path()
    cmd.write_text(
        "@echo off\r\n"
        f'set "PYTHONPATH={src};%PYTHONPATH%"\r\n'
        f'"{py}" -m mld autopatch >> "{log}" 2>&1\r\n',
        encoding="utf-8",
    )
    minutes = max(10, int(interval // 60))
    for name, extra in ((WIN_TASK, ["/SC", "MINUTE", "/MO", str(minutes)]),
                        (WIN_TASK_LOGON, ["/SC", "ONLOGON"])):
        r = subprocess.run(["schtasks", "/Create", *extra, "/TN", name,
                            "/TR", f'"{cmd}"', "/F"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError("schtasks failed: " + (r.stderr or r.stdout).strip()[:400])
    return cmd


def windows_uninstall() -> None:
    for name in (WIN_TASK, WIN_TASK_LOGON):
        subprocess.run(["schtasks", "/Delete", "/TN", name, "/F"], capture_output=True)


def windows_status() -> str:
    r = subprocess.run(["schtasks", "/Query", "/TN", WIN_TASK],
                       capture_output=True, text=True)
    return "registered" if r.returncode == 0 else "not registered"


def install(asar_path: Path, interval: int) -> str:
    if sys.platform == "darwin":
        return str(macos_install(asar_path, interval))
    if sys.platform == "win32":
        return str(windows_install(interval))
    raise RuntimeError("automatic re-patching is supported on macOS and Windows; "
                       "run `mld autopatch` from your own scheduler on this platform")


def uninstall() -> None:
    if sys.platform == "darwin":
        macos_uninstall()
    elif sys.platform == "win32":
        windows_uninstall()
    else:
        raise RuntimeError("unsupported platform")


def status() -> str:
    if sys.platform == "darwin":
        return macos_status()
    if sys.platform == "win32":
        return windows_status()
    return "unsupported platform"