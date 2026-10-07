# Compatibility

| Component | Initial official source release |
| --- | --- |
| Repository tag | `v0.1.0-rc.4` |
| Python distribution / import | `haltseal-payments-evaluation==0.1.0rc4` / `haltseal_payments_sdk` |
| JavaScript | `@haltseal/payments-evaluation@0.1.0-rc.4` |
| Runtime | Python 3.12+; Node 22+; ESM |
| API profile | Payment API RC4; `mode: local-evaluation`; `production: NO_GO` |
| Fixtures | SDK sandbox `1.0.0`; fixed synthetic USD 10 |
| Evaluation routes | `A`, `B`, `C` only |
| Distribution | GitHub release files; npm/PyPI publication not claimed |
| Production | Not qualified; `NO_GO` |

Tag, package versions and fixture version describe different components.
This is the clients' source home, not a new kernel release. Runtime/type files
match public RC4. Documentation and reproducible archive metadata are
maintained here, so complete hashes can differ from the website archives.

Pin exact prereleases, verify checksums and rerun recovery tests on upgrade.
Preserve unresolved original identities across any version change.
