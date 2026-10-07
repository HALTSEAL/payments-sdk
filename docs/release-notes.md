HALTSEAL Payments SDK registry beta candidate.

`0.2.0-rc.2` adds canonical package names and explicit single-language hosted
fixture commands while preserving the v2 exact-original client runtime/types.
Python's import remains `haltseal_payments_sdk`; Node imports `@haltseal/payments`.
Legacy RC4 and v2 RC1 archives remain unchanged. Use this release's checksums.

PyPI/npm publication is pending owner setup. See `docs/registry-release.md` for
publisher values, first npm upload, OIDC release checks and package-name migration.
Run `python3 tools/quickstart.py` for an offline comparison of both clients.

Evaluation only. Fixed synthetic fixtures, no real funds, no native-provider or
retained-kernel qualification. Production remains NO_GO.

Browser sandbox: https://haltseal.com/sandbox/
Workflow pilot: https://haltseal.com/pricing/#workflow
