# mirasim-lan-direct

[English](README.md) | [简体中文](README.zh-CN.md)

Make a selected **Mirasim** cloud space connect to its host **directly over the
LAN** instead of through `relay.mirasim.ai`.

Not affiliated with Mirasim / Mirofish. Use it on machines you own, with your
own spaces. See [Disclaimer](#disclaimer).

---

## Why this exists

A Mirasim desktop window for a cloud space always opens a gateway socket at
`wss://relay.mirasim.ai/v2/gateway/ws`. Three things in the shipped app make a
LAN connection impossible out of the box:

1. The renderer's cloud-target builder injects `gatewayUrl` for every cloud
   entry, and the transport chooses the gateway before it ever looks at a direct
   candidate.
2. The cloud directory entry carries an empty `e2e` field, so a hand-made LAN
   target cannot complete the encrypted handshake.
3. The renderer Content-Security-Policy does not allow `ws://<LAN-IP>:*`, so even
   a correct direct attempt is blocked and silently falls back to the relay.
4. A direct v2 connection that authenticates with the shared token makes the
   host store a new legacy device row on every connection. The patch sends a
   stable `installId`, so the host supersedes the previous row.

This tool rewrites the target builder (injecting the host's address, shared
token and E2E public key; removing `gatewayUrl`/`grant` for direct targets, or
keeping them for hybrid) and widens the CSP for the configured LAN origins. It finds the function by its shape, so it does
not depend on the app's hashed asset names.

## Requirements

- Python 3.9+ (standard library only; no third-party dependencies)
- The Mirasim desktop app installed
- One of:
  - SSH access to the host (the pair endpoint is loopback-only), or
  - a copy of the host's `pair` JSON, or
  - the host's token, E2E public key and cloud node id

## Quick start (macOS)

```sh
git clone https://github.com/jornlin/mirasim-lan-direct.git
cd mirasim-lan-direct

# read the host's pair data over SSH and write the config
PYTHONPATH=src python3 -m mld init --ssh my-host --app /Applications/Mirasim.app

# build + install (quits and relaunches Mirasim)
PYTHONPATH=src python3 -m mld patch --restart

# verify: reachability + installed marker
PYTHONPATH=src python3 -m mld check

# optional: re-apply automatically after every app update
PYTHONPATH=src python3 -m mld agent install
```

Or install the command once:

```sh
python3 -m pip install -e .
mld init --ssh my-host
```

> If the app is already patched by an older version of this tool and you no
> longer have an unpatched copy, add `--original /path/to/app.asar.orig` to
> `init` (it is kept for future rebuilds).

## Quick start (Windows)

```powershell
git clone https://github.com/jornlin/mirasim-lan-direct.git
cd mirasim-lan-direct

$env:PYTHONPATH = "src"
py -3 -m mld init --ssh my-host
py -3 -m mld patch --restart
py -3 -m mld check
py -3 -m mld agent install      # Scheduled Task: logon + every 10 min
```

If the app is installed under `Program Files`, install the task from an
elevated PowerShell. The task calls the same CLI; no re-signing is needed on
Windows (Authenticode signs the executable, not `app.asar`).

## 中文速览

完整中文说明见 [README.zh-CN.md](README.zh-CN.md)。

非官方工具：把你自己账号下的某个 Mirasim 云空间改成**局域网直连**，不走 `relay.mirasim.ai`。只在自己拥有的机器和空间上使用。

```sh
git clone https://github.com/jornlin/mirasim-lan-direct.git
cd mirasim-lan-direct

# 1) 初始化：通过 SSH 读取主机的 pair 数据（也可 --pair 导入 JSON）
PYTHONPATH=src python3 -m mld init --ssh my-host --app /Applications/Mirasim.app

# 2) 打补丁（会退出并重开 App）
PYTHONPATH=src python3 -m mld patch --restart

# 3) 检查：目标是否可达、装的是哪个补丁
PYTHONPATH=src python3 -m mld check

# 4) 可选：升级后自动重打
PYTHONPATH=src python3 -m mld agent install
```

- 地址/端口：`--host 192.168.1.50:4939` 可重复，工具会挑第一个可达的；换网段、多台主机都只需改配置。
- 配置在 `~/Library/Application Support/mirasim-lan-direct/config.json`（0600，含 token，不要提交）。
- Windows：`py -3 -m mld init --ssh my-host`，其余相同；`mld agent install` 注册计划任务。
- 回滚：`mld restore`（会停用自动重打）。
- 已知边界：App 升级会覆盖补丁（代理会重打）；改的是渲染层，不是厂商源码；未来版本改了代码形状会安全失败。

## Configuration: IPs, ports, multiple hosts

All addresses and credentials live in `config.json`, outside the repository:

- macOS: `~/Library/Application Support/mirasim-lan-direct/config.json`
- Windows: `%APPDATA%\mirasim-lan-direct\config.json`
- Linux: `$XDG_CONFIG_HOME/mirasim-lan-direct/config.json`
- override: `MLD_CONFIG_DIR=/path mld ...`

Ways to provide a target:

```sh
mld init --ssh my-host --port 4939
mld init --pair pair.json
mld init --node pc-... --host 192.168.1.50:4939 --host 10.0.0.5:4939 \
         --token ... --e2e ...
```

- `--host` is repeatable. The patcher tests each address and uses the first
  reachable one; the rest stay as fallbacks for later resolution.
- `--port` (default `0`) auto-discovers the host's server port from
  `~/.mirasim/run/local-*.token`. The desktop app may restart on 4970, a manual
  `serve` on another port; SSH init and refresh follow it.
- Ports are part of the host string (`host:port`) and the SSH fetch (`--port`).
- Run `mld init` again with another `--node` to add more spaces; each target is
  patched independently.
- `--app` points at a non-default install (`Mirasim.app`, or the Windows install
  directory). The app root is stored in the config for the background agent.

The config is written `0600` on POSIX and contains a bearer token. Never commit
it. `.gitignore` already excludes it. Automatic pair refresh (token/E2E/hosts)
only runs when the config has an `ssh` target; without SSH, re-run `mld init`
after the host changes.

## Collaboration: direct, hybrid, member, gateway

- **direct** — LAN only. No cloud identity/presence/chat; use it when a space
  does not need collaboration.
- **hybrid** — LAN session/terminal/file data plus a gateway link for
  collaboration. Recommended for the owner's own devices on a cloud-attached
  space.
- **member** — another account in the space: gateway chat/tasks/presence plus
  LAN data with the member's g2 grant. Needs the optional host verifier.
- **gateway** — everything through the relay. Use it as a fallback if the
  hybrid/member gateway half cannot authenticate, or when you want one link.

```sh
mld mode <node-id-or-label> hybrid       # owner devices: LAN data + collab
mld mode <node-id-or-label> direct       # LAN only
mld mode <node-id-or-label> gateway      # relay only
mld member <node-id-or-label>            # another account: LAN data + gateway tasks
```

### Hybrid details

Hybrid keeps a **gateway link** for everything collaborative — presence,
member and channel/chat protocol, turn and attention watches, session access,
member usage, and cloud/member administration — and sends session, terminal,
file, snapshot and prompt data over the **LAN**.

Two renderer details are required and are handled by the patch:

- the direct link sends `clientHello {remoteByChoice: true}` before `ready`, so
  the host does not treat the LAN client as a same-machine local client;
- the composite client reports `managed: true` from the gateway half, so the
  window draws the cloud/collaboration layout rather than the local one.

The space must still be cloud-attached and the gateway half must authenticate
(the target keeps its cloud grant). If the gateway half cannot authenticate,
switch back to `gateway` mode.

### Legacy direct/hybrid: owner devices only

The legacy modes embed the host's shared token and open a LAN connection with
`role=admin`. That connection has no gateway viewer identity, so the host's
chat identity falls back to its **own signed-in owner account**. Use them only
on devices signed into the **same account as the host**, and never distribute
the shared token. For a different account, use the member mode below.

### Members with their own account (member mode)

`member` mode is for other people in a shared space. It does not use the shared
token:

```sh
mld member <node-id-or-label>        # no grant file needed
mld check                            # member (cloud grant)
```

Owner setup for another device:

```sh
mld invite <node-id-or-label>        # prints node/host/e2e and the commands
```

On the member device:

```sh
mld init --member --node <id> --host <ip:port> --e2e <host key>
mld patch --restart
```

No shared token is read or written.

The target keeps the cloud `gatewayUrl` and `grant`, drops `token`, and runs as
a two-link hybrid:

- **gateway** carries chat/channel, presence, task dispatch and member
  administration — the relay supplies the requester credential that agent
  turns need;
- **LAN direct** carries sessions, terminals, files and snapshots, using the
  member's g2 gateway session as the account grant. The host verifier also
defaults non-owner account devices on an attached host to `member` (add the
account to `mirachannelMachineAdmins` if it should have admin data access).

First enrollment needs a small host-side verifier (the host normally accepts
only g1 enroll grants on its direct listener):

```sh
# on the host (the computer that owns the space)
python3 scripts/host-g2-auth.py --apply
# rollback:
python3 scripts/host-g2-auth.py --restore
```

After the first successful direct connection the host stores a normal
`via=account` device with the member's `accountId`; later reconnects use the
device keys (`via=known`) and do not need the short-lived session again.
An app update replaces `server-main.cjs`, so re-apply the host patch after
updating Mirasim. See [docs/host-g2-auth.md](docs/host-g2-auth.md).

`mld check` also reports `host auth: member g2/role verifier present` when the
config has an SSH target; a missing verifier is called out with the apply
command. If the gateway half cannot authenticate, use official `gateway` mode
instead.

### Finding a member grant (diagnostic)

The desktop client normally supplies the g2 session automatically. To inspect
what the local cloud RPC returns on a member device (tokens/email redacted):

```sh
node scripts/probe-cloud.mjs
# no Node? Electron as Node:
ELECTRON_RUN_AS_NODE=1 /Applications/Mirasim.app/Contents/MacOS/Mirasim scripts/probe-cloud.mjs
```

Look for claims with `sub` (member account), `aud` (host node id) and `exp`.
`mld member <node> --grant-file member.jwt` can still pin an explicit grant if
you have one; the normal path needs no file.

### Direct collab gate (legacy)

`mld collab <node> on` can force the renderer's presence gate for a direct
target, but the host's presence service still decides whether the space is
collaborative. Prefer `hybrid` when collaboration matters.

## Switching modes

One command switches a space and applies it (Mirasim restarts):

```sh
mld mode <node-id-or-label> direct|gateway|hybrid
```

- `direct` — LAN data, no gateway/collab.
- `gateway` — relay/gateway, full collaboration.
- `hybrid` — collaboration over the gateway, LAN for session data.

Add `--stage` to only write the config (then `mld patch --force --restart`).
A restart is required because the transport target is baked into the window's
renderer; changing it rebuilds `app.asar`.

## Commands

| Command | What it does |
|---|---|
| `mld init` | fetch/import target data and write the config |
| `mld patch [--force] [--dry-run] [--restart]` | build and install the renderer patch |
| `mld mode <node> direct\|gateway\|hybrid` | switch a space and apply it (`--stage` to only configure) |
| `mld init --member ...` | create a member target without the shared token |
| `mld invite <node>` | print node/host/e2e and member setup commands (no token) |
| `mld member <node>` | other account: gateway collab + LAN data (optional `--grant-file`) |
| `mld check` | show app version, installed marker, target mode/reachability, agent state |
| `mld autopatch` | agent entry point: patch only if missing/stale/unreachable |
| `mld restore` | restore the pristine `app.asar` and disable the agent |
| `mld agent install\|uninstall\|status` | manage the background re-patcher |
| `mld doctor` | paths, permissions, app/binary presence |

`mld patch` refuses to install while the app is running unless `--restart` is
given. `--dry-run` builds and validates in memory without touching the app.

## Automatic re-patching

`mld agent install` creates:

- macOS: a LaunchAgent (`io.github.mirasim-lan-direct.autopatch`) with
  `WatchPaths` on `app.asar`, `RunAtLoad`, and a `StartInterval` (default 300 s).
- Windows: Scheduled Tasks at logon and every 10 minutes running
  `mld autopatch`.

The agent runs a copy of the package under `<config dir>/runtime`, so moving or
deleting the cloned repository does not break it (re-run `mld agent install` to
update that copy after changing the code).

On every run the agent:

1. refreshes the host's pair data at most every 6 hours (if `--ssh` was used),
2. compares the installed marker with the current target hash,
3. checks that the configured origins are reachable,
4. rebuilds from the pristine copy of the current app version if needed,
5. validates the patched JavaScript with the app's own Electron binary
   (`ELECTRON_RUN_AS_NODE=1 ... --check`),
6. quits Mirasim, backs up the original asar, installs, relaunches.

If the host is unreachable, the agent keeps the existing patch and does not
restart the app. A stale lock (crash/SIGKILL) is cleared after 15 minutes.

The agent only re-patches the client `app.asar`. The optional host g2 verifier
(`scripts/host-g2-auth.py`) lives in the host's `server-main.cjs`, which a
Mirasim update also replaces; re-apply it on the host after updating.

Logs: `<config dir>/autopatch.log`. Backups: `<config dir>/backups/`.

Disable: `mld agent uninstall`, or `mld restore` (which also writes a `DISABLED`
flag). Re-enable with `mld patch` or by removing `DISABLED`.

On macOS, a LaunchAgent-run interpreter may be blocked by App Management/TCC
from writing inside `/Applications`. Manual `mld patch` still works; to keep
automatic re-patching, grant `/usr/bin/python3` Full Disk Access (and App
Management, if listed) in System Settings → Privacy & Security, then run
`mld agent install` again. The installer probes the destination before quitting
and relaunches Mirasim even if the write fails, so a denied agent cannot leave
the app closed.

## Rollback

```sh
mld restore
```

Restores the newest pristine `app.asar` whose version matches the installed
app, then relaunches. It refuses to install a mismatched build.

## How it works

See [docs/how-it-works.md](docs/how-it-works.md). Short version:

- `src/mld/asar.py` — dependency-free asar reader/writer
- `src/mld/patch.py` — shape-based function rewrite + CSP widening + JS validation
- `src/mld/hostinfo.py` — pair fetch over SSH, address normalisation, reachability
- `src/mld/system.py` — app discovery, backups, locking, process control
- `src/mld/agent.py` — LaunchAgent / Scheduled Task
- `src/mld/cli.py` — the `mld` command

## Limitations

- The app's resource seal becomes invalid (`codesign --verify` reports one
  modified file). The Mach-O signature is untouched; on macOS the app still
  launches and `spctl` accepts it. An app update overwrites the patch; the agent
  re-applies it.
- The tool depends on the shape of one minified function and on the renderer
  CSP. A future app version that changes either will make `mld patch` fail
  safely (the app is left untouched, the old patch or relay keeps working).
- The host's shared token is embedded in the patched `app.asar`. On POSIX the
  file is chmod 600; on Windows mind the install directory ACL.
- A legacy (shared-token) device leaves a bounded history on the host (200
  entries); the stable `installId` keeps one active row, and the UI hides
  revoked rows.
- `mirachannelStrictAuth` on the host will reject the shared token; direct
  routing then falls back to the relay.
- Leaving the LAN makes the direct route fail and fall back to the relay.
- Member mode needs the optional host g2 verifier for the first direct
  enrollment. The enrolled `via=account` device persists until revoked; removing
  a member from the space stops new sessions, so also revoke their stored device
  to cut existing LAN access. The host's `server-main.cjs` is replaced by app
  updates; re-apply `scripts/host-g2-auth.py`.
- Member mode is hybrid: chat/task dispatch and presence still use the gateway;
  only session/terminal/file data is direct. A pure direct link cannot supply
  the requester credential agent turns need.

## Development

```sh
make test       # unittest suite, no app required
make compile
```

The tests build a synthetic asar (no Mirasim code or assets are included) and
exercise parsing, repacking, the function rewrite, CSP handling, and the
behaviour of the patched function via Node.

## Disclaimer

This is an unofficial tool. It modifies a third-party application's resources on
your own computer and relies on a feature of your own account. It is not
affiliated with, endorsed by, or supported by Mirasim or Mirofish. Patching the
app may violate its terms of service; you are responsible for how you use it.
The software is provided "as is", without warranty of any kind. See
[LICENSE](LICENSE).
