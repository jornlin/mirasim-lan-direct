# Changelog

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