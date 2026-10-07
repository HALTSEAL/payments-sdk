# Contributing

Use synthetic reproductions. Report security findings via [SECURITY.md](SECURITY.md).
Run `python3 tools/check.py` with Python 3.12+ and Node 22+ before a PR.
Recovery changes need a shared case passing in both installed clients.

Do not add automatic modifying retries, fallback, telemetry, runtime dependencies
or provider credentials without design review. Do not import private kernel
source or service history. RC4 archives remain pinned. Runtime changes require
a new version and explicit reviewed migration hashes. V2 is recorded in
`release-baseline/v2-migration.json`; refresh its reviewed hashes after reviewing
a change, then run installed-package checks. Never rewrite published tags or assets.
