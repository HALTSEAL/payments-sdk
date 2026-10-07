# Compatibility

| Component | SDK v2 evaluation release |
| --- | --- |
| Repository tag | `v0.2.0-rc.1` |
| Python distribution / import | `haltseal-payments-evaluation==0.2.0rc1` / `haltseal_payments_sdk` |
| JavaScript | `@haltseal/payments-evaluation@0.2.0-rc.1` |
| Runtime | Python 3.12+; Node 22+; ESM |
| API profile | Payment API RC5 response guards and retained RC4 HTTP fixtures; `mode: local-evaluation`; `production: NO_GO` |
| Fixtures | SDK sandbox `1.0.0`; fixed synthetic USD 10 |
| Evaluation routes | `A`, `B`, `C` only |
| Distribution | GitHub release files; npm/PyPI publication not claimed |
| Production | Not qualified; `NO_GO` |

Tag, package versions and fixture version describe different components.
This is the clients' source home, not a new kernel release. SDK v2 has a new
runtime and version; the original RC4 archives remain unchanged. The reviewed
upgrade is recorded in `release-baseline/v2-migration.json`. Use this SDK
release's checksums rather than those of a different API/website release.

Responses must echo exact operation/obligation identities and supply complete
attempt records. A gateway returning earlier incomplete shapes needs to
upgrade its response contract; rejection preserves uncertainty.

Pin exact prereleases, verify checksums and rerun recovery tests on upgrade.
Preserve unresolved original identities across any version change.
