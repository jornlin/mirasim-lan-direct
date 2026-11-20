# Security

## What this tool handles

- A **host access token** and the host's **E2E public key**, read from the
  host's `/mirachannel/pair` endpoint or supplied on the command line.
- A **patched `app.asar`** that embeds that token, so the app can authenticate
  to the host over the LAN. Member mode instead keeps a short-lived cloud g2
  session at runtime and embeds no shared token.

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

## Member mode and the host verifier

Member mode uses a Mirasim-issued g2 gateway session as the first direct
account grant. The optional `scripts/host-g2-auth.py` adds a verifier to the
host's `server-main.cjs`. It checks the g2 signature (shipped public key),
`kind=gateway`, the host cloud node id in `aud`, `sub`, and expiry; it does not
store the session. The first successful connection stores a normal
`via=account` device with the member's account id, so later connections use
device keys. Revoke that device when the member leaves; space removal alone
stops new sessions but does not delete an already enrolled device.

The script also changes the attached-host role fallback so a non-owner account
device is `member`, not `admin`; the owner and `mirachannelMachineAdmins`
entries stay admin. The script backs up `server-main.cjs` and supports
`--restore`. A Mirasim update replaces that file; re-apply the verifier. The host patch is security-sensitive:
review the script before running it and keep the host's device/account list
under the same care as the space membership list.

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
