# Changelog

## 0.5.0 — 2026-11-21

- Member mode is hybrid: the cloud `gatewayUrl` + g2 session are kept; chat,
  presence, task dispatch and member administration use the gateway (which
  supplies the requester credential agent turns need), while sessions,
  terminals, files and snapshots use the LAN with the g2 grant. No shared
  token is embedded.
- `mld member <node>` no longer needs a grant file; the client uses the cloud
  gateway session automatically. An explicit `--grant/--grant-file` still
  works for diagnostics.
- Add `scripts/host-g2-auth.py`: optional host verifier that accepts a g2
  gateway session as a direct account grant (`kind=gateway`, `aud` = host
  cloud node id, `sub`, `exp`). The first enrollment stores a normal
  `via=account` device; later reconnects use device keys (`via=known`).
  Includes backup/restore and a syntax check.
- Document the host patch, its update lifecycle and revocation model.

## 0.4.0 — 2026-11-21

- Member mode prototype: automatic cloud gateway session as the direct grant,
  `managed`/`remoteByChoice` flags, and JWT validation for explicit grants.

## 0.3.0 — 2026-11-20

- Member-grant mode: `mld member <node> --grant-file <jwt>` uses a
  platform-signed account grant (`sub` = member account, `aud` = host node)
  instead of the shared token. The host's `Flo` account path records
  `via=account`, so `wn`/`identify` return the member and their role; the
  target keeps `host`/`e2e`/`grant` and no `gatewayUrl`/`token`.
- The renderer still gets `clientHello remoteByChoice`, `managed:true` and the
  collaboration layout. `mld check` shows the grant subject and expiry.
- Requires the member's account to be in the host's
  `mirachannelSharedAccounts` (join the space first). The grant itself must be
  obtained from Mirasim's account/device pairing or cloud flow; the tool does
  not mint it. Until a grant is available, members stay on the official gateway.

## 0.2.2 — 2026-11-20

- Direct collaboration without a gateway: a `direct` target with `collab`
  enabled now wraps the LAN client with `clientHello {remoteByChoice:true}`,
  `managed:true` and the original-`post` capture. Verified on 0.0.828: chat,
  presence and the collaboration layout work over a single LAN link.
- Document the identity boundary: a legacy LAN connection is `role=admin` and
  has no gateway viewer, so the host's chat identity falls back to its own
  signed-in owner account. Direct/hybrid are therefore for the owner's own
  devices; other members must use the official gateway/cloud client, and the
  patched app/shared token must not be distributed.

## 0.2.1 — 2026-11-20

- Documentation: recommend hybrid for LAN data + collaboration; document the
  `clientHello remoteByChoice` / `managed` layout flags and the exact
  gateway-vs-LAN frame split.
- Drop a redundant collab route (`chat*` already covers it); add regression
  coverage for `clientHello`, `managed`, and `setWorkspaceMembers` routing.
- Probe that `app.asar` is writable before quitting, and relaunch Mirasim even
  when backup/install fails. A macOS App Management denial no longer leaves the
  app closed.

## 0.2.0 — 2026-11-20

Hybrid is now usable for a cloud space that is attached to an account.

- Route the whole collaboration protocol over the gateway: `presenceUpdate`,
  `tasksenseFocus`, turn/attention watches, session access, member usage,
  `chat*`, `peer*`, messaging session lists, member-workspace and
  cloud/controlled-space administration. Session, terminal, file, snapshot and
  prompt data stays on the LAN link.
- Send `clientHello {remoteByChoice: true}` on the direct link before the
  client's `ready` (and on every reconnect). The host otherwise treats the
  same-machine legacy connection as local (`clientLocal: true`), which makes
  the renderer draw its local messenger layout.
- Expose `managed: true` from the gateway half on the composite client; the
  renderer only picks the cloud/collaboration layout when the client is
  managed (or client-local).
- Expose the gateway's `setHello`; broadcast `ready`, `clientVisibility`,
  stream cadence and settings push to both links so the gateway connection is
  admitted and can replay its hello after a reconnect.
- Capture the direct `post` before the renderer can wrap it and honour a
  `post` override, preventing the composite's self-call recursion.
- Remove temporary diagnostics. Patch revision 12.

## 0.1.15 — 2026-11-20

- Hybrid: expose `managed: true` on the composite client. The renderer picks
  its local/messenger layout (and draws the “this computer isn't a collab
  space” card) unless `client.managed === true`; the official gateway client
  carries that flag, the direct `Ss` client does not. Patch revision 11.

## 0.1.14 — 2026-11-20

- Hybrid: send `clientHello {remoteByChoice: true}` on the direct link before the
  client's `ready`. The host otherwise sees a same-machine/loopback-style
  legacy client (`clientLocal: true`), so the window draws the local messenger
  layout and the “this computer isn't a collab space” card even though the
  space is attached and collaboration is live. Direct state is authoritative
  again; the gateway state is only used for presence/chat frames. Patch
  revision 10.

## 0.1.13 — 2026-11-20

- Hybrid: make the gateway's state frame authoritative for the window UI.
  The direct legacy state reports `chatPersonal: true` (so the UI shows “this
  computer isn't a collab space yet”), while the gateway state carries the
  attached/shared chat flags. Forward the full gateway state, suppress later
  direct state frames, and replay the last gateway state to new subscribers.
  Patch revision 9.

## 0.1.12 — 2026-11-20

- Hybrid: route the collaboration protocol (chat/channels/peers/messaging
  member lists) over the gateway link, not the direct link. The direct host
  does not serve the collab chat/member API for a legacy connection, which left
  the members rail empty even though presence was live. Session/terminal/file
  data still uses the LAN link. Patch revision 8.

## 0.1.11 — 2026-11-20

- Diagnostics: log presence roster size, viewer, and frame-subscriber count.

## 0.1.10 — 2026-11-20

- Hybrid: mirror the gateway's `state.collab` into the direct state (the
  renderer's collaboration UI is gated by `hostState.collab`, which a direct
  state may not set), expose the gateway's `setHello`, and broadcast the client
  lifecycle frames (`ready`, `clientVisibility`, stream cadence, settings push)
  to both links so the gateway connection is admitted for presence. Temporary
  `MLD` console diagnostics. Patch revision 6.

## 0.1.9 — 2026-11-20

- Fix the hybrid composite's real recursion: the renderer wraps a client's
  `post` by assigning to it, and the proxy's `post` forwarded through the
  target's now-wrapped `post`, calling itself forever. Capture the original
  direct `post`, honour an assigned `post` override, and add a `set` trap so
  the wrapper chain terminates. Patch revision 5.

## 0.1.8 — 2026-11-20

- Harden the hybrid composite against re-entrant callbacks: iterate over a
  snapshot of frame/connection subscribers and drop synchronous re-entrant
  frames. Patch revision 4.

## 0.1.7 — 2026-11-20

- Fix the hybrid composite's initial `onConnection(false)` callback recursion
  (renderer `Maximum call stack size exceeded`); connection callbacks are now
  delivered asynchronously and only for an already-connected link. Stable
  method identities avoid re-subscription churn. Patch revision 3.

## 0.1.6 — 2026-11-20

- `mld mode <target> <mode>` now applies the switch (patch + restart) in one
  command; `--stage` only writes the config. `mld check` prints each target's
  mode.

## 0.1.5 — 2026-11-20

- Experimental `hybrid` mode: a composite transport keeps the gateway link for
  presence/collab/turn-activity frames while session and data frames use the
  direct LAN link. `mld mode <node> hybrid`; fall back to `gateway` if the
  gateway half cannot authenticate.

## 0.1.4 — 2026-11-20

- Optional collab presence for a direct target: `mld collab <node|label> on`
  forces the renderer's presence gate and sets `globalThis.__mldCollab` when the
  target is built. The host's presence service still gates on the space's cloud
  attach; if the UI does not activate, use gateway mode.

## 0.1.3 — 2026-11-20

- Per-space `mode`: `direct` (LAN, no gateway) or `gateway` (relay, keeps cloud
  collaboration identity). `mld mode <node|label> direct|gateway`; re-apply
  with `mld patch --force --restart`.

## 0.1.2 — 2026-11-20

- Pass `installId` into the mirachannel transport options. The target and the
  final target builder already carried it, but the transport dispatcher
  (`xs`) dropped it, so the v2 HELLO never sent `client.installId` and the host
  still stored a new legacy device per connection.
- Include a patch revision in the marker hash, so an agent notices when a
  newer rewrite is required.

## 0.1.1 — 2026-11-20

- Inject a stable `installId` into the direct target (and pass it through the
  final target builder). The host now revokes the previous legacy device row
  instead of adding a new one on every connection.
- Discover the host's server port from `~/.mirasim/run/local-*.token` on SSH
  init/refresh; the host can restart on a new port (the desktop app uses 4970).
- Refresh pair data when no configured origin is reachable, not only on the
  6-hour timer.
- Recognize an older marker-less patch by the rewritten function signature, so
  a changed host/port still rebuilds from the pristine copy instead of failing.
- `mld patch` clears the `DISABLED` flag; deduplicate the changed-file list.

## 0.1.0 — 2026-11-20

- Initial public layout.
- Dependency-free asar reader/writer with offset and SHA-256 integrity rebuild.
- Shape-based rewrite of the cloud-target builder; multiple targets supported.
- CSP widening for configured LAN origins.
- Validation of patched JavaScript with the app's own Electron binary.
- `mld init|patch|check|autopatch|restore|agent|doctor`.
- macOS LaunchAgent and Windows Scheduled Task generation.
- Pristine-source tracking per app version, versioned backups, stale-lock
  recovery, host-down protection, and token-fingerprint health checks.