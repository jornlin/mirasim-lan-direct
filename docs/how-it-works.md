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

- direct spaces get `host`, `token`, `e2e`, no `gatewayUrl`/`grant`;
- hybrid spaces additionally keep `gatewayUrl`/`grant` and carry `"h":1`
  (plus `"c":1` for the renderer's collab gate);
- every other cloud space is byte-for-byte behaviourally unchanged;
- the trailing comment is the version/health marker (a hash of the targets,
  including the mode and patch revision).

### Stable device identity

With the shared token, the host's v2 legacy authentication
(`Yto.legacy`) calls its device factory for every connection. That factory
supersedes a previous record only when the new connection carries the same
`installId` or the same noise key; the app's cloud path provides neither, so
each connection added a new "可连接的设备" row.

The patched target now carries a stable, generated `installId`, and the final
target builder (`$e`) passes it through, so the v2 HELLO includes
`client.installId`. The host revokes the previous legacy record with the same
id and returns a new active one; the roster stays at one active row (the UI
hides revoked rows; the on-disk history is capped at 200).

### Hybrid transport

A hybrid target keeps both routes. The transport dispatcher still returns a
mirachannel client, but wraps it in a composite:

- the **direct** client carries sessions, terminals, files, snapshots and
  prompts, and its `state` frame is the window's authoritative state;
- a managed **gateway** socket carries `presenceUpdate`, `tasksenseFocus`,
  turn/attention watches, session access, member usage, `chat*`/`peer*`,
  messaging session lists, member workspaces and cloud/member administration;
- `ready`, `clientVisibility`, stream cadence and settings push are sent to
  both links, and the gateway's `setHello` is exposed so its hello frames are
  replayed after a reconnect;
- the direct link sends `clientHello { remoteByChoice: true }` before `ready`
  and on every reconnect. The host computes
  `clientLocal = trusted && !remoteByChoice`; without it, a same-LAN legacy
  client looks local and the renderer draws its local messenger layout.
- the composite reports `managed: true` from the gateway half. The renderer's
  layout chooser uses that flag (alongside `clientLocal`) to pick the
  cloud/collaboration shell.

The direct `post` is captured before the renderer can replace it. The renderer
wraps `post` by assignment; forwarding through the target's current `post`
would call that wrapper recursively. A proxy `set` trap records the wrapper and
the composite always terminates at the captured original.

### Port discovery

The host's server port is not fixed: the desktop app defaults to 4970, while a
manual `serve` may use another port. On SSH init/refresh the tool lists
`~/.mirasim/run/local-*.token`, tries the configured port first, then every
other port, and stores the one that answers `/mirachannel/pair`. If no
configured origin is reachable, `autopatch` refreshes the pair immediately
instead of waiting for the 6-hour timer.

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

## Identity on each link

The host derives a connection's chat identity in `identify(conn)`:

- a gateway connection has a `viewer` injected by the relay, so it acts as that
  member with their role;
- a legacy LAN connection has no viewer. Its role is `admin`, so the host falls
  back to its own signed-in account and treats the client as the **owner**.

That is why direct and hybrid are owner-device modes. The shared token is also
an admin bearer secret: distributing it to another member would give them the
owner's data access. Other members should use the official gateway client,
which carries their own viewer identity.

## Member grants

The host's `Flo` authenticator also accepts a platform-signed account grant:

```js
grant -> verify with enrollKey.pub
      -> aud == nodeId
      -> sub == host account or sharedAccounts[]
      -> via "account", accountId = sub
```

The member then appears through `wn`/`identify` as their own account with the
shared space's role, not as the host owner. A target can carry such a grant:

```js
{
  mode: "remote", host: "http://192.168.1.50:4970",
  token: "", grant: "<jwt>", e2e: "<host key>",
  nodeId: "...", collab: true
}
```

The direct client still sends `clientHello {remoteByChoice:true}` and the
composite reports `managed:true`, so the renderer uses the remote collaboration
layout. The grant must be issued by Mirasim's account/device pairing or cloud
flow; the tool does not mint it. `mld member` only validates its JWT shape,
`aud` and `exp`.

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