# Compatibility

## Tested against

| App build | Platform | Result |
|---|---|---|
| 0.0.828 | macOS (arm64) | patched; direct single-link collaboration and hybrid verified |
| 0.0.827 | macOS (arm64) | patched, direct LAN verified |
| 0.0.824 | macOS host | pair/CSP/transport verified |
| 0.0.824 | Windows | not yet verified on a real Windows machine |

The patcher is shape-based, so minor builds should keep working. The two shapes
it relies on are:

1. the cloud-target function:
   `const <v>=<p>.gatewayUrl??"";return{mode:"remote",host:""`
2. the renderer CSP's `connect-src` / `img-src` / `media-src` / `object-src` /
   `frame-src` directives in `dist/renderer/index.html`.

If either disappears, `mld patch` fails before writing anything. The old patch
or the relay keeps working.

## Finding a new shape

After an app update that breaks patching, search the installed archive:

```sh
python3 - <<'PY'
import sys
sys.path.insert(0, "src")
from mld import asar
a = asar.load("/Applications/Mirasim.app/Contents/Resources/app.asar")
for p, d in a.contents.items():
    if p.endswith(".js") and b"gatewayUrl??" in d:
        i = d.find(b"gatewayUrl??")
        print(p, d[max(0, i - 120):i + 160].decode("utf-8", "replace"))
PY
```

Open an issue with the app version and the printed snippet (redact any tokens).

## Platform notes

- macOS: the app remains vendor-signed at the Mach-O level; only the resource
  seal is invalid. `spctl` still accepts it. TCC permissions are tied to the
  executable signature and are unaffected.
- Windows: Authenticode signs the executable, not `app.asar`; no re-signing is
  needed.
- Linux: the desktop app ships as AppImage/deb. Point `--app` at the install
  root containing `resources/app.asar`. Automatic re-patching is not generated
  by `mld agent install` on Linux; use the systemd user timer in
  `scripts/linux/`.