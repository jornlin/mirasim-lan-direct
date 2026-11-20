# Security

## What this tool handles

- A **host access token** and the host's **E2E public key**, read from the
  host's `/mirachannel/pair` endpoint or supplied on the command line.
- A **patched `app.asar`** that embeds that token, so the app can authenticate
  to the host over the LAN.

The token is a bearer credential for the host's mirachannel endpoint. Treat it
like a password.

## Storage

- Runtime config: `<config dir>/config.json`, written mode `0600` on POSIX.
  The directory is outside the repository.
- Patched app: the tool sets `app.asar` to `0600` on POSIX. On Windows, check
  the install directory ACL; `Program Files` is normally readable by all local
  users.
- Backups under `<config dir>/backups/` contain the *unpatched* app and no
  secrets.
- Logs contain node ids and addresses, not tokens.

## Repository hygiene

The repository contains no vendor application code, no extracted assets, no
tokens, no pair data, and no patched archives. `.gitignore` excludes runtime
configuration and artifacts. Do not paste real tokens or pair JSON into issues
or pull requests; redact them.

## Threat model

This is a local tool that modifies a locally installed application. It does not
run a network service and does not send data anywhere. The main risks are:

- a leaked token (config file or patched `app.asar`) being used by another
  local user or process;
- a supply-chain compromise of this repository (review the code; it is short
  and dependency-free);
- a future app update changing the patched code shape; the tool fails closed
  and leaves the app untouched rather than installing a broken archive.

## Reporting

Please open a private security advisory on the repository (or email the
maintainer if no advisory is available). Do not include real credentials.
