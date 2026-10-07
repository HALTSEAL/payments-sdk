HALTSEAL Payments SDK evaluation prerelease RC2.

`0.2.0-rc.2` adds canonical package names and explicit single-language hosted
fixture commands while preserving the v2 exact-original client runtime/types.
Python's import remains `haltseal_payments_sdk`; Node imports `@haltseal/payments`.
Legacy RC4 and v2 RC1 archives remain unchanged. Use this release's checksums.

Python `haltseal-payments==0.2.0rc2` is published on PyPI. JavaScript is available
as the exact GitHub release tarball; npm publication remains pending. See
`docs/registry-release.md` for verified publication evidence, the remaining npm
setup and package-name migration.
Run `python3 tools/quickstart.py` for an offline comparison of both clients.

Evaluation only. Fixed synthetic fixtures, no real funds, no native-provider or
retained-kernel qualification. Production remains NO_GO.

Browser sandbox: https://haltseal.com/sandbox/
Workflow pilot: https://haltseal.com/pricing/#workflow
