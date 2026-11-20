# Troubleshooting

Start with:

```sh
mld check
mld doctor
```

`check` prints the installed marker, the expected marker, each target's
reachability, and the agent state.

## It still goes through the relay

- `mld check` says `installed: not patched` → run `mld patch --restart`.
- `installed:` shows a marker but `expected:` differs → run
  `mld patch --force --restart` (the targets/token/address changed).
- `target: … UNREACHABLE` → the chosen LAN address is not reachable from this
  machine. Add another `--host` with `mld init`; the tool tests each address.
- The app was not restarted after patching → close it and open it again, or use
  `--restart`.
- The host's `mirachannelStrictAuth` is on → the shared token is rejected and
  the client falls back to the relay. Turn it off on the host, or pair a device.
- The renderer console shows `Connecting to 'ws://…' violates … Content Security
  Policy` → the CSP patch did not apply; rebuild.
- The host has `lanDirectEnabled=false` → the LAN listener is off. Enable
  “允许同一网络内直连” in the host's remote-access settings.

## `expected exactly one cloud-target function, found 0`

Either the installed asar is already patched (the original shape is gone) or the
app changed its code shape.

- If it is already patched: use `--force` so the tool rebuilds from a pristine
  copy (`app.asar.orig` or a version backup).
- If the app changed: the tool cannot patch this version yet. The app was left
  untouched (relay still works). Open an issue with the app version and the
  output of `grep -a 'gatewayUrl??' app.asar` (redact secrets).

## `no pristine app.asar for version …`

The installed app is patched and no unpatched copy of this version is known.
Provide one:

```sh
mld patch --force --original /path/to/unpatched/app.asar
```

or reinstall the app, then `mld init` again.

## `Mirasim is running`

Close the app before `mld patch`, or pass `--restart` to let the tool quit and
relaunch it. Installing while the app runs is refused because Electron may read
archive offsets lazily.

## The app does not start after patching

Restore the backup:

```sh
mld restore
```

Then check `codesign --verify /Applications/Mirasim.app` (a sealed-resource
error is expected) and the agent log. If the app is in a broken state, reinstall
it; the tool never modifies the executable.

## macOS: the agent exits with 78 / 126

`launchd` may be denied reading files under `~/Downloads`, `~/Desktop`, or
`~/Documents` (TCC). `mld agent install` copies the package to
`<config dir>/runtime` so the repository's location does not matter; the config
directory itself must not be under one of those TCC-protected folders. Check
`autopatch.log` and `launchctl print
gui/$(id -u)/io.github.mirasim-lan-direct.autopatch`.

## Windows: `app.asar not found`

Pass the install root:

```powershell
py -3 -m mld init --ssh my-host --app "$env:LOCALAPPDATA\Programs\Mirasim"
```

Common roots are `%LOCALAPPDATA%\Programs\Mirasim` (per-user) and
`C:\Program Files\Mirasim` (per-machine; writes need an elevated task).

## Windows: the task runs but nothing happens

- `py`/`python` must be on the task's PATH.
- Open `%APPDATA%\mirasim-lan-direct\autopatch.log`.
- Check `schtasks /Query /TN "Mirasim LAN Direct"`.
- For a per-machine install, re-register from an elevated PowerShell.

## SSH pair fetch fails

The pair endpoint is loopback-only. The tool runs, on the host:

```sh
ssh my-host 'T=$(cat ~/.mirasim/run/local-4939.token); curl -fsS "http://127.0.0.1:4939/mirachannel/pair?token=$T"'
```

If that fails: check the SSH key (`BatchMode` is used), the host's port, and
whether `~/.mirasim/run/local-*.token` exists. As a fallback, copy the JSON
output to a file and use `mld init --pair pair.json`.

## Collaboration mode won't activate

- On the **owner's own devices**, use hybrid (LAN data + gateway chat):
  `mld mode <node|label> hybrid` then `mld patch --force --restart`.
- For **other accounts**, use member mode:
  `mld member <node|label>` then apply. It keeps the gateway for chat, presence
  and task dispatch (the relay supplies the requester credential) and uses the
  LAN for session/terminal/file data with the member's g2 grant.
- Member mode's first enrollment needs the optional host verifier:
  on the host, `python3 scripts/host-g2-auth.py --apply`, then restart Mirasim.
  `--restore` rolls it back.
- `needs-requester` / “没带上请求人的凭证” means a pure direct link was used for
  chat/task frames. Use member mode (hybrid), not pure direct.
- `account enrollment refused (bad-signature)` means the host did not accept the
  g2 session: the host verifier is missing/stale, or the g2 public key/`aud`
  check is wrong. Re-apply `scripts/host-g2-auth.py`; the expected claim is
  `kind=gateway`, `aud=<host cloud node id>`, `sub=<member account>`.
- Check `mld check`: a member target prints `member (cloud grant)` and, when
  SSH is configured, `host auth: member g2/role verifier present`. A missing
  line or MISSING means run `scripts/host-g2-auth.py --apply` on the host.
- Host logs should show `via=grant`/`via=known ... remote=10.x` for the member's
  data link and `via=gateway` for chat. `via=legacy` means the shared-token
  target was used instead of member mode.
- `mirachannelSharedAccounts` is not required by the g2 verifier; the g2
  session is the authorization. After a member leaves, revoke their stored
  `via=account` device to cut existing LAN access.
- Member direct data defaults to `role=member` on an attached host. If the
  account must have admin data access, add it to `mirachannelMachineAdmins`
  (owner stays admin). Chat on the gateway follows the space role.
- Do not run a second mirasim server on a host that is already a collab space.
  An SSH/remote server staged in `~/.mirasim-remote` defaults to the same
  `MIRASIM_HOME` and competes for the space program, rendezvous registration
  and the space key files. Stop it and restart the app; the log lines to look
  for are `space program: cannot listen on 127.0.0.1:4963` and a rendezvous that
  stays `off`.

## “可连接的设备” keeps growing

An older client patch authenticated with the shared token but sent no
`installId`, so the host stored a new legacy device on every connection.
Update to 0.1.1+, apply the patch, and restart. To clean the accumulated rows,
edit the host's `~/.mirasim/devices.json` (back it up first) and keep only
entries where `via != "legacy"` or `id == "legacy-shared-token"`; the host reads
the file on the next device event.

## Direct stopped after the host restarted

The host's port may have changed (the desktop app defaults to 4970). Run
`mld init --ssh my-host` or let `autopatch` refresh; the tool discovers
`local-*.token` ports automatically. `mld check` shows the current target.

## The app update overwrote the patch

Expected. The agent re-applies it within the configured interval (or immediately
via `WatchPaths`). If the agent is not installed, run `mld patch --restart`.

## Logs

- `<config dir>/autopatch.log` — agent/CLI actions
- `~/Library/Logs/...` or the app's own logs — renderer CSP/WebSocket errors

## The autopatch agent logs `Operation not permitted`

A LaunchAgent runs `/usr/bin/python3` outside the terminal that installed the
patch. macOS App Management (TCC) may then refuse to create
`app.asar.new` inside `/Applications/Mirasim.app`, even though `mld patch`
works from the terminal.

- Manual patching is unaffected: run `mld patch --force --restart` after an
  app update.
- To restore automatic re-patching, grant the background interpreter
  **Full Disk Access** (and **App Management**, if listed) in
  System Settings → Privacy & Security, adding `/usr/bin/python3`
  (Cmd+Shift+G to type the path), then run `mld agent install` again.
- The installer now relaunches Mirasim even when the write fails, so a denied
  agent cannot leave the app closed. If the agent cannot patch, disable it with
  `mld agent uninstall` until the permission is granted.
