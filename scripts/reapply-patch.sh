#!/usr/bin/env bash
# Re-apply the mirasim-lan-direct renderer patch after a Mirasim update.
# Quits Mirasim, patches, verifies, then relaunches it.
#
# Usage:
#   scripts/reapply-patch.sh                    # normal rebuild
#   scripts/reapply-patch.sh --force            # extra args are passed to `mld patch`
#   scripts/reapply-patch.sh --allow-running    # patch in place, no quit/relaunch
#   MLD_APP=/path/to/Mirasim.app scripts/reapply-patch.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="${MLD_APP:-/Applications/Mirasim.app}"
BINARY="$APP/Contents/MacOS/Mirasim"
LOG_DIR="$HOME/Library/Application Support/mirasim-lan-direct"
LOG="$LOG_DIR/reapply.log"

if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PY="$ROOT/.venv/bin/python"
else
  PY="$(command -v python3 || true)"
fi
[[ -n "$PY" ]] || { echo "error: python3 not found" >&2; exit 1; }
[[ -d "$APP" ]] || { echo "error: app not found: $APP (set MLD_APP)" >&2; exit 1; }
[[ -f "$ROOT/src/mld/cli.py" ]] || { echo "error: run this from the mirasim-lan-direct checkout" >&2; exit 1; }

mld() { PYTHONPATH="$ROOT/src" "$PY" -m mld "$@"; }

is_running() {
  # Read ps to completion: `grep -q` exits early, and with pipefail the
  # writer's SIGPIPE would make a genuine match look like a miss.
  local lines
  lines="$(ps -axo command=)"
  [[ $'\n'"$lines"$'\n' == *$'\n'"$BINARY"$'\n'* ]]
}

quit_app() {
  is_running || return 0
  echo "==> quitting Mirasim"
  osascript -e 'tell application "Mirasim" to quit' >/dev/null 2>&1 || true
  for _ in $(seq 1 20); do
    is_running || { echo "    quit"; return 0; }
    sleep 0.5
  done
  echo "    still running; forcing"
  pkill -f "^$BINARY\$" 2>/dev/null || true
  for _ in $(seq 1 10); do
    is_running || return 0
    sleep 0.5
  done
  return 1
}

relaunch() {
  if ! is_running; then
    echo "==> launching Mirasim"
    open -a "$APP" || true
  fi
}
trap relaunch EXIT

mkdir -p "$LOG_DIR"

ALLOW_RUNNING=0
for arg in "$@"; do
  [[ "$arg" == "--allow-running" ]] && ALLOW_RUNNING=1
done
if [[ $ALLOW_RUNNING -eq 1 ]]; then
  # The app keeps the old asar until its next launch; do not quit or relaunch.
  trap - EXIT
fi

echo "==> app: $APP"
if [[ $ALLOW_RUNNING -eq 0 ]]; then
  quit_app || {
    echo "error: could not quit Mirasim" >&2
    echo "       run inside the app? use --allow-running, then restart it yourself" >&2
    exit 1
  }
fi

echo "==> patching"
if mld patch --app "$APP" "$@"; then
  status=0
else
  status=$?
  echo "error: mld patch failed (exit $status)" >&2
fi

echo "==> checking"
set +e
check_out="$(mld check 2>&1)"
check_status=$?
set -e
echo "$check_out"
verdict="$(printf '%s\n' "$check_out" | sed -n 's/^verdict:  *//p' | head -n1)"

{
  printf '%s reapply: patch=%s check=%s verdict=%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$status" "$check_status" "${verdict:-unknown}"
} >>"$LOG"

if [[ $status -ne 0 || $check_status -ne 0 ]]; then
  echo "FAILED: see output above and $LOG" >&2
  exit 1
fi
echo "OK: patch installed ($verdict)"
