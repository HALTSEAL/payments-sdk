# Compatibility

| Component | Registry beta candidate | Retained SDK v2 RC1 |
| --- | --- | --- |
| SDK tag | `v0.2.0-rc.2` | `v0.2.0-rc.1` |
| Python distribution | `haltseal-payments==0.2.0rc2` | `haltseal-payments-evaluation==0.2.0rc1` |
| Python import | `haltseal_payments_sdk` | `haltseal_payments_sdk` |
| JavaScript import | `@haltseal/payments` | `@haltseal/payments-evaluation` |
| Distribution | GitHub candidate; registry publication pending | GitHub release files |
| Financial client runtime | Same v2 guards and types; Python version constant changes | Exact-original guards and total caller deadlines |
| Explicit packaged fixture demos | Python module and npm demo binary | Source examples |

Runtime requirements are Python 3.12+ or Node 22+ (ESM and TypeScript declarations).
The public fixture profile is SDK sandbox `1.0.0`, fixed synthetic USD 10. SDK
versions, API profiles and sandbox campaign versions describe different components.

Client response guards align with the Payment API RC5 evaluator contract and the
retained RC4 HTTP fixture response shapes. The website's pinned sandbox bundle
continues to include its original RC4 SDK archives. The separately published
Sandbox v2 campaign is a bounded engine/provider evaluation, not this SDK version.

All public examples remain `mode: local-evaluation`, `production: NO_GO`, with
fixed routes `A`, `B`, `C`. No managed production payment endpoint is provided by
installing this SDK. Gateway response validation and native-provider qualification
are separate boundaries.

`release-baseline/v2-migration.json` is preserved. The registry candidate's
packaging/version/demo changes are pinned separately in `registry-beta.json`.
Legacy archives are unchanged. Pin exact versions and use that release's checksums.
Preserve every unresolved original identity across package upgrades.
