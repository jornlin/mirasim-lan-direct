# Changelog

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