# Changelog

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