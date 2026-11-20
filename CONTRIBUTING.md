# Contributing

Thanks for helping. A few ground rules keep this project publishable:

1. **No vendor code or assets.** Do not commit Mirasim source, extracted
   `app.asar` contents, screenshots that reveal credentials, or patched
   archives. The tests build their own synthetic asar.
2. **No real credentials.** Never commit `config.json`, pair JSON, tokens, or
   logs from a real host. Redact node ids/addresses in issues if they are
   sensitive.
3. **Standard library only** in the runtime package. The tool must run on a
   stock Python 3.9+ installation.
4. **Tests must not require Mirasim.** `make test` uses a synthetic archive; the
   JavaScript behaviour test skips when Node is unavailable.

## Development

```sh
git clone https://github.com/<you>/mirasim-lan-direct.git
cd mirasim-lan-direct
make test
```

Style: small modules, type hints, no side effects at import time, clear error
messages. Keep the patcher fail-closed: if the target function or CSP cannot be
found exactly once, raise and leave the app untouched.

## Pull requests

- Describe the app version you tested against (if you tested against a real app).
- Include a test for parser/patcher changes (a synthetic asar can reproduce the
  shape).
- Do not bump the version or edit the changelog unless asked.
- By contributing you agree your changes are licensed under the MIT license.
