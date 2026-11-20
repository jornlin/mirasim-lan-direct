# How it works

## The normal path

A cloud space is described by an entry in the renderer's cloud directory. A
window for that space resolves the entry through a small function (minified as
`L` in current builds):

```js
function L(e) {
  const t = e.gatewayUrl ?? "";
  return {
    mode: "remote", host: "",
    token: e.token ?? "",
    ...(K(e) && !e.token ? { grant: e.grant } : {}),
    ...(typeof e.grantAt === "number" ? { grantAt: e.grantAt } : {}),
    ...(t ? { gatewayUrl: t } : {}),
    nodeId: e.nodeId, e2e: e.e2e,
    rendezvous: e.rendezvous || M,
    ...N(e)                       // v2 cert/relay/lease/issuer
  };
}
```

The transport then sees `gatewayUrl` and opens a gateway socket first:

```js
if (target.mode === "remote" && target.gatewayUrl && target.nodeId && grant) {
  return gatewaySocket(target.gatewayUrl, ...);   // wss://relay.mirasim.ai/...
}
```

Only when there is no gateway does it build the mirachannel route list, where a
LAN WebSocket has the best tier (0), WebRTC is next (1), and the relay is the
fallback (2).

Two more details block a hand-made direct target:

- the cloud entry's `e2e` is empty, so the encrypted handshake has no key;
- the renderer CSP's `connect-src` lists localhost and the Mirasim hosts, not
  the LAN origin, so the browser refuses `ws://<LAN>:4939/...`.

## What the patch changes

For each configured target (`nodeId`, `origin`, `token`, `e2e`) the patched
function carries a lookup table:

```js
function L(e) {
  const Q = {"pc-…": {"o": "http://10.0.0.5:4939", "t": "…", "k": "…"}};
  const d = Q[e.nodeId];
  return {
    mode: "remote",
    host:  d ? d.o : (e.host ?? ""),
    token: d ? d.t : (e.token ?? ""),
    ...(d ? {} : (K(e) && !e.token ? { grant: e.grant } : {})),
    ...(e.grantAt >= 0 ? { grantAt: e.grantAt } : {}),
    ...(!d && e.gatewayUrl ? { gatewayUrl: e.gatewayUrl } : {}),
    nodeId: e.nodeId,
    e2e: d ? d.k : e.e2e,
    rendezvous: e.rendezvous || M,
    ...N(e)
  };
}
/*mirasim-lan-direct:<hash>*/
```

- configured spaces get `host`, `token`, `e2e`, no `gatewayUrl`/`grant`;
- every other cloud space is byte-for-byte behaviourally unchanged;
- the trailing comment is the version/health marker (a hash of the targets).

The CSP patch adds, for each configured host:

- `connect-src`: `http://host:* ws://host:*`
- `img-src`, `media-src`, `object-src`, `frame-src`: `http://host:*`

The wildcard port also covers page/artifact previews served by the host.

## Why the function is found by shape

The renderer assets have content-hashed names (`default-space-<hash>.js`), which
change on every build. Searching for the code shape
`const <v>=<p>.gatewayUrl??"";return{mode:"remote",host:""` is stable across
versions. Exactly one match is required; zero or several means the app changed
and the tool refuses to write anything. The minified names of the helper
functions (`K`, `N`, the rendezvous constant) are read from the matched
function itself, so a bundler rename does not silently produce calls to
undefined identifiers.

## Validation

Before installing, the patched JavaScript is written to a temporary file and
checked by the app's own Electron binary:

```sh
ELECTRON_RUN_AS_NODE=1 /Applications/Mirasim.app/Contents/MacOS/Mirasim --check file.mjs
```

On Windows the same works with `Mirasim.exe`. A syntax error aborts the build;
the app is never replaced with an archive that would not load.

The archive is also re-serialized with recomputed offsets and SHA-256 integrity
blocks, then re-read and verified in memory.

## Backups and rebuild sources

- When the installed `app.asar` is unpatched, it is the source and is backed up
  before installation as `backups/app.asar.<version>.<time>` (plus a `.version`
  sidecar).
- When it is already patched (for example `--force` after a token/IP change),
  the tool rebuilds from a pristine copy of the same app version: the imported
  original (`<config dir>/app.asar.orig`) or a version-matching backup.
- If no pristine copy exists, the command fails and leaves the app untouched;
  pass `--original`.

## The background agent

`mld autopatch` is idempotent:

1. take a lock (stale after 15 minutes);
2. exit if `DISABLED` exists;
3. refresh pair data over SSH at most every 6 hours;
4. resolve a reachable origin per target;
5. read the installed marker and compare it with the target hash;
6. if the marker matches and origins are reachable, exit;
7. if a legacy marker (older tool version) is present and a target is reachable,
   exit without restarting the app;
8. if no target is reachable, keep the current patch and exit;
9. otherwise rebuild, validate, quit the app, back up, install, relaunch.

The macOS LaunchAgent triggers on `WatchPaths(app.asar)`, at login, and on a
timer. Windows uses Scheduled Tasks. Both invoke the same CLI.