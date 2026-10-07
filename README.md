# HALTSEAL Payments SDK

**One obligation. One right to pay.**

Official Python and JavaScript clients for the HALTSEAL Payment API. When a
payment request loses its reply, keep its identity and look up the original.
Application calls never automatically resend or select a replacement route.

**Evaluation prerelease: `0.2.0-rc.2`.** Python is published on
[PyPI](https://pypi.org/project/haltseal-payments/0.2.0rc2/). JavaScript is
available from the pinned GitHub release; **npm publication is pending**.
This is a synthetic evaluation prerelease; production remains `NO_GO`.

[Browser sandbox](https://haltseal.com/sandbox/) ·
[API docs](https://haltseal.com/docs/payments/) ·
[Release downloads](https://github.com/HALTSEAL/payments-sdk/releases) ·
[Recovery contract](docs/recovery.md)

## Choose your language

Python requires Python 3.12+; JavaScript requires Node 22+. Each hosted exercise
needs only its own language and an internet connection. No HALTSEAL account,
provider credentials or real funds are needed.

Install the pinned release for your language and run the fixed exercise:

```sh
# Python, in a virtual environment
python3 -m venv .venv
. .venv/bin/activate
python -m pip install haltseal-payments==0.2.0rc2
python -m haltseal_payments_sdk.sandbox --output python-sandbox.json
```

```sh
# JavaScript / TypeScript, in your project, from the GitHub release
npm install --ignore-scripts --no-audit --no-fund \
  https://github.com/HALTSEAL/payments-sdk/releases/download/v0.2.0-rc.2/haltseal-payments-0.2.0-rc.2.tgz
npx --no-install haltseal-payments-demo --output javascript-sandbox.json
```

Expected result:

```text
PASS: original lookup; UNKNOWN HOLD; closure; stale HOLD; fresh ACCEPT; PAID REFUSE.
Synthetic dispatches: 2. Original lookup redispatches: 0.
```

The Python activation command above is for macOS/Linux; on Windows use
`.venv\Scripts\Activate.ps1` in PowerShell. JavaScript installs the canonical
`@haltseal/payments` package from GitHub, so imports remain `@haltseal/payments`.
An npm registry install by package name is not available yet. See
[release verification and registry status](docs/registry-release.md).

These explicit commands connect only to `https://haltseal.com` fixed HTTP
fixtures. A short-lived synthetic session is created for the exercise. The
record omits its key. A new output filename is required; existing records are
never overwritten. `--help` describes the optional loopback fixture override.
Imports and package installation do not start a session or make a payment call.
The hosted fixture has session/call limits and no production availability promise.

## What the exercise establishes

| Step | Expected behavior |
| --- | --- |
| Original creation reply is withheld | Retain `UncertainDispatch` and the original operation ID |
| Look up that exact operation | Historical decision; `redispatched: false` |
| Another route while the original is unresolved | `HOLD` |
| Observe injected original closure | `OBSERVED`, `CLOSED` |
| Replacement with the old approval | `HOLD` |
| Fresh approval after closure | `ACCEPT` and the predefined `PAID` fixture |
| Another route after payment | `REFUSE` |

The fixtures demonstrate client integration and recovery handling. They do not
establish native-provider behavior, independent kernel verification, customer
deployment or production readiness. `ACCEPT` is authorization, not settlement.

## Install from release files or reproduce offline

The GitHub releases also provide pinned wheel/tarball files, source,
`manifest.json`, `SHA256SUMS.txt` and build provenance. Verify each release's own
checksums. Legacy RC4 and v2 RC1 archives keep their original names and bytes.

For the RC2 canonical archives:

```sh
python -m pip install --no-index --no-deps ./haltseal_payments-0.2.0rc2-py3-none-any.whl
npm install --offline --ignore-scripts --no-audit --no-fund ./haltseal-payments-0.2.0-rc.2.tgz
```

To build and run both installed clients against a local fixture without registry
access, use the source checkout (Python 3.12+ and Node 22+ are required):

```sh
python3 tools/quickstart.py
python3 tools/check.py
```

The local host closes when the command finishes. This deeper offline comparison
is separate from the single-language hosted example.

## Integrate with your configured evaluator

Python imports remain `haltseal_payments_sdk`; JavaScript imports now use
`@haltseal/payments`. See [package-name migration](docs/registry-release.md)
and [version compatibility](docs/compatibility.md). An SDK installation
supplies a client and an explicit fixture demo, not a payment evaluator.

Persist the intended request and identity before dispatch. On creation
uncertainty, look up the same operation. On resume/cancel/recover uncertainty,
read the same attempt. `HOLD` and `REFUSE` block the new financial step. A timeout,
lookup `404` or unavailable reply does not establish original closure.

SDK v2 validates exact operation/obligation echoes and complete attempt records.
Both languages preserve original recovery context and bound the whole caller
request. See [recovery](docs/recovery.md), [v2 migration](docs/migration-v2.md) and
[security boundaries](docs/security-model.md).

## Evaluate your workflow

If two software paths can release the same obligation, bring one workflow and
its original/replacement behavior to the
[scoped pilot](https://haltseal.com/pricing/#workflow). Review its current price,
readiness conditions and scope before requesting evaluation.

## Scope and license

MIT covers the published clients and fixed fixtures. The retained payment kernel,
native adapters, issuer keys and customer records are excluded. Production remains
`NO_GO`. [Security](SECURITY.md) · [Contributing](CONTRIBUTING.md) ·
[Changelog](CHANGELOG.md) · [Release boundaries](docs/release-scope.md)
