# Host g2 authentication for member mode

`mld member` lets another account use the LAN for session/terminal/file data
while chat and task dispatch stay on the gateway. The first direct connection
presents the member's short-lived **g2 gateway session** as an account grant.

The shipped host accepts only **g1 enroll grants** on its direct mirachannel
listener. `scripts/host-g2-auth.py` adds a second verifier to the host's `Flo`
enrollment branch and fixes the attached-host default role:

- verify the g2 signature with the g2 public key that ships with the host;
- require `kind: "gateway"`, `aud` = the host's cloud node id, a `sub`, and an
  unexpired `exp`;
- return `via: "account"`, `accountId: sub`, and the claim's role;
- change the `LYr` fallback so a non-owner account device on an **attached**
  host is `member`, not `admin`. Without this, an empty
  `mirachannelMachineAdmins` made every account device admin. The owner account
  and entries in `mirachannelMachineAdmins` stay admin; managed-harness hosts
  keep their old default.

No cloud credential is minted or forwarded. A valid g2 session is already
issued by Mirasim to an account that can open this machine.

## Apply

On the host (the computer that owns the space):

```sh
python3 scripts/host-g2-auth.py --apply
# syntax check only:
python3 scripts/host-g2-auth.py --check
# rollback:
python3 scripts/host-g2-auth.py --restore
```

The script writes a timestamped sibling backup:
`server-main.cjs.mld-bak`. Restart Mirasim after applying or restoring.

## Lifecycle

1. The member opens the space in a patched member client.
2. The host records a normal `via=account` device with the member's
   `accountId`; the g2 session is only used for this enrollment.
3. Later reconnects use the device keys (`via=known`) and do not depend on the
   10-minute session expiry.
4. Removing the member from the space stops new sessions. Revoke the stored
   account device in the host's device list to cut existing LAN access; the
   g2 verifier intentionally does not consult `mirachannelSharedAccounts`.

## Update / rollback

- A Mirasim update replaces `server-main.cjs`; run `--apply` again. Existing
  `via=known` member devices keep working until then, but new enrollments fail.
- `--restore` restores the backup taken by the most recent `--apply`.
- The patch is shape-based on the `Flo` grant branch. If the app changes that
  code, `--apply` refuses rather than writing a partially patched host.

## Security notes

- The g2 session is a bearer credential for this node. The verifier checks its
  signature, audience and expiry; it does not check space membership again.
  The cloud only issues it to an account that can open the machine.
- The resulting device is a normal account device; revoke it from the host's
  device list when someone leaves. Direct data runs as `member` unless the
  account is in `mirachannelMachineAdmins`; chat on the gateway still uses the
  space role from the relay.
- The patch does not enable g2 on the gateway listener (the relay already
  authenticates those); it only affects direct mirachannel enrollment.