# HALTSEAL Payments SDK

**One obligation. One right to pay.**

Official Python and JavaScript clients for the HALTSEAL Payment API evaluation.
When a payment request loses its reply, retain its identity and look up the
original. The SDK does not automatically retry or select another route.

**SDK v2 · `0.2.0-rc.1`** strengthens exact-original response verification and
total caller deadlines. This is an evaluation prerelease, not production activation.

[![SDK checks](https://github.com/HALTSEAL/payments-sdk/actions/workflows/quality.yml/badge.svg)](https://github.com/HALTSEAL/payments-sdk/actions/workflows/quality.yml)

[Browser sandbox](https://haltseal.com/sandbox/) ·
[API docs](https://haltseal.com/docs/payments/) ·
[Release downloads](https://github.com/HALTSEAL/payments-sdk/releases) ·
[Recovery contract](docs/recovery.md)

## Run the recovery example

Python 3.12+ and Node 22+ are required. No account, live credentials, external
runtime packages or real funds are needed.

```sh
git clone https://github.com/HALTSEAL/payments-sdk.git
cd payments-sdk
python3 tools/quickstart.py
```

This verifies the preserved RC4 baseline and reviewed v2 migration, builds and installs both packages into
temporary environments, starts a local synthetic HTTP server and runs both
clients. It closes the server when finished. No provider or kernel is called.

```text
PASS: original lookup; UNKNOWN HOLD; closure; stale HOLD; fresh ACCEPT; PAID REFUSE.
Synthetic dispatches: 2. Original lookup redispatches: 0.
```

| Scenario | Expected behavior |
| --- | --- |
| Original creation reply is withheld | `UncertainDispatch`; retain the operation ID |
| Look up that exact operation | Historical decision; `redispatched: false` |
| Another route while the original is unresolved | `HOLD` |
| Observe the injected original closure | `OBSERVED`, `CLOSED` |
| Replacement with the old approval | `HOLD` |
| Fresh approval after closure | `ACCEPT` with the predefined `PAID` fixture |
| Another route after payment | `REFUSE` |

These are **fixed synthetic fixtures**. They demonstrate client integration
and recovery handling. They are not native-provider results, independent
kernel verification or proof of production readiness.

## Install one client

Download the wheel or tarball and `SHA256SUMS.txt` from a
[versioned release](https://github.com/HALTSEAL/payments-sdk/releases), verify
the checksum, then install the local file:

```sh
python3 -m pip install --no-index --no-deps ./haltseal_payments_evaluation-0.2.0rc1-py3-none-any.whl
npm install --offline --ignore-scripts --no-audit --no-fund ./haltseal-payments-evaluation-0.2.0-rc.1.tgz
```

The package names are `haltseal-payments-evaluation` and
`@haltseal/payments-evaluation`. PyPI/npm registry publication is not claimed.
JavaScript includes TypeScript declarations and uses ESM.

Python imports from `haltseal_payments_sdk`; JavaScript imports from
`@haltseal/payments-evaluation`. Complete runnable examples live in
[examples/recover-original](examples/recover-original).

## Preserve recovery identity

1. Persist the operation ID and intended request **before** creation.
2. Check the decision. `HOLD` and `REFUSE` block the new financial step.
3. On `UncertainDispatch`, retain the recovery context. Look up the same
   operation for creation; read the same attempt for resume/cancel/recover.
4. A timeout, lookup `404` or unavailable reply does not establish closure.
   Preserve the hold and investigate the original.

`ACCEPT` is an authorization decision, not proof of payment. The client adds
no business-level retry, fallback or replacement authority. Read the
[method map and errors](docs/recovery.md).

## What v2 verifies

| Boundary | Client behavior |
| --- | --- |
| Exact original | Creation and lookup must echo the requested operation ID |
| Payment identity | Creation must match the obligation; nested attempt identities must agree |
| Retained obligation | Pass it to original lookup for an additional independent check |
| Complete records | Attempt reads and nested records require all typed identity, amount, state and evidence fields |
| Observation summaries | `OBSERVED` must match the attempt ID and state; expanded records must be complete |
| Whole transport deadline | Connection, headers, body and validation share one caller deadline |
| Uncertain modifying call | Retain `UncertainDispatch` and the original context; no automatic resend |

Python: `client.lookup_operation(error.operation_id, obligation_id=error.obligation_id)`.
JavaScript: `client.lookupOperation(error.operationId, {obligationId: error.obligationId})`.
Keep the retained obligation with your original request. A timeout cannot prove
that the server stopped or that the original payment is closed.

[Upgrade from RC4](docs/migration-v2.md) · [Security boundaries](docs/security-model.md)

## Verify what you install

```sh
python3 tools/check.py
python3 tools/build_release.py --output dist
```

Checks install built packages outside the source checkout, run 29 shared HTTP
fault cases and 101 response identity/record cases in each language, execute the
examples and compare two clean builds byte for byte. The RC4 archives stay
unchanged; `release-baseline/v2-migration.json` pins the reviewed v2 runtime.
Verify the new release's own checksums. The API profile and SDK version are separate.

| Path | Contents |
| --- | --- |
| `packages/python` | Python client, typed results and recovery context |
| `packages/javascript` | JavaScript client and TypeScript declarations |
| `examples/recover-original` | The same recovery sequence in both languages |
| `tests` | Shared failure matrix and local synthetic fixtures |
| `tools` | Offline builder, quickstart and verification |
| `docs` | Recovery, compatibility and release boundaries |

## Evaluate your workflow

If two software paths can release the same payment obligation, bring one
workflow and its original/replacement behavior to the
[scoped pilot](https://haltseal.com/pricing/#workflow). The site lists the
current price, readiness conditions and scope. The next proof is a reviewed
workflow qualification. Contact [scott@haltseal.com](mailto:scott@haltseal.com).

## Scope and license

This is an **evaluation release**. Production remains `NO_GO`.
The clients and synthetic fixtures are MIT licensed. The retained kernel,
provider adapters, signing keys and customer records are excluded. This
license grants no rights to excluded components.

[Security](SECURITY.md) · [Contributing](CONTRIBUTING.md) ·
[Changelog](CHANGELOG.md) · [Release boundaries](docs/release-scope.md)
