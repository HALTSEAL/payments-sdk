# ADK: agent changes, retained payment identity

**One obligation. One right to pay. Even when the agent changes.**

This repository example puts the unchanged HALTSEAL Python SDK behind three
host-bound Google ADK `FunctionTool`s. A real `LlmAgent` and `InMemoryRunner`
execute scripted model responses. No model API key, HALTSEAL account, real funds
or external service is needed after dependency installation. The existing fixed
HTTP fixture runs only on loopback and closes when the command finishes.

The example establishes ADK tool wiring and recovery handling against those
fixtures. Its evidence label is `ADK_FIXED_HTTP_FIXTURE_EVALUATED`. It does not
qualify the payment kernel, a native provider, a customer workflow or production.
The model is scripted; this does not evaluate LLM reasoning or prompt resistance.
Production remains `NO_GO`.

## Run from this source checkout

Python 3.12+ and Node 22+ are required; the checked environment uses Python 3.12,
Node 24 and Google ADK 2.11.0. Dependencies belong to the example only. The
published SDK has no ADK dependency and its version and runtime are unchanged.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r examples/adk/requirements.txt
python examples/adk/demo.py --output adk-synthetic-result.json
python -m unittest discover -s tests -p test_adk_tools.py -v
```

On Windows, activate with `.venv\Scripts\Activate.ps1` in PowerShell. Run these
commands from the repository root. Dependency installation requires registry
access; the exercise itself uses loopback HTTP, with no model API calls.
Use a new output filename: existing evidence records are never overwritten.
The ADK files are in the repository, not the already-published RC2 archives.

Expected final output:

```text
PASS: ADK repeat/handoff; UNKNOWN HOLD; stale HOLD; one fixture winner; PAID REFUSE; local STOP.
Main fixture dispatches: 2. Separate stop fixture: 1. Original lookup redispatches: 0.
Scripted model, real ADK runtime. Fixed HTTP fixtures; production NO_GO.
```

ADK may also print framework warnings or token-usage messages for the scripted
model. The JSON record contains actual tool responses and HTTP fixture traces,
framework/SDK versions, checks and limitations. It excludes fixture API keys.

## What to show a buyer

| Request or event | Observed result |
| --- | --- |
| Original reply is withheld after a synthetic dispatch | Tool returns `HOLD`; submission intent remains retained |
| Same agent asks again | No second SDK submission; exact-operation lookup remains available |
| A new agent, ADK session and tool object take over | The trusted host supplies the original identity and submitted intent; no new send |
| A backup agent supplies invented IDs, route, approval and a closure claim | These are not tool parameters; the host binding is retained and the unresolved fixture returns `HOLD` |
| The host injects and observes original closure | The old approval still returns `HOLD` |
| The host injects fresh approval; two independent adapters compete | One fixed-fixture request is admitted; its predefined `PAID` result blocks the other |
| Another route asks after that payment | `REFUSE` |
| In a separate fixture, the application stops while the original is `UNKNOWN` | No new submission; the original remains unresolved and reserves capacity; read recovery remains available |

There are two synthetic dispatches in the main fixture: the original, then the
post-closure replacement. This is not a claim that only one request may ever
be submitted. The original must be closed without effect before the fixture
allows a freshly approved replacement. The competing winner is immediately
`PAID` by definition of this fixture; the example is not a general concurrency
proof. Historical `ACCEPT` is an old authorization result, not a new send or
proof of settlement.

## Keep authority in the trusted host

`payment_tools.py` exposes only `request_payment()`, `lookup_payment()` and
`stop_payment_requests()`. Their function signatures accept no model arguments.
For the pinned ADK version, unknown arguments are discarded by `FunctionTool`;
the guards test that they cannot replace the captured host values.

The host binds the obligation, operation, route and approval revision before
constructing the tools. Model output, agent names, ADK session IDs and future
A2A task/context IDs are not economic identities. Closure injection and fresh
approval are trusted demo controls and never appear in the agent's tool list.
There is no direct provider-send tool that can bypass the SDK boundary.

The example journal and stop latch are in memory outside ADK. The handoff
explicitly reconstructs a submitted journal; it does not test a process crash
or distributed persistence. In an actual application, authorize the binding,
persist submission intent before IO, rehydrate it after restart, and coordinate
every worker and path through the connected evaluator. A new journal, token,
agent or conversation must not create a fresh obligation for the same debt.
The example's local latch covers only tools sharing that `PaymentControls`
object. It cannot stop another process or retract an already submitted request.

`HOLD`/`REFUSE`, an unavailable reply and lookup `404` do not authorize a new
financial step. No agent assertion, runner cancellation or local stop establishes
authoritative no-effect closure. Enforcement must cover the actual execution
path: do not turn an `ACCEPT` result into a separate, unguarded bank-send call.

## Connect an actual workflow next

Bring one workflow's original and replacement software paths, its identity
mapping, recovery owner and HOLD/REFUSE stop branch to the
[Workflow Evaluation Kit](../../docs/evaluate-your-workflow.md). That separately
supplied evaluator can observe connected local customer hooks; this ADK fixture
pass cannot substitute for that evidence. Native-provider and production
qualification remain separate.

If your application already uses ADK, reuse this narrow tool surface with the
trusted application binding and your configured nonproduction evaluator. An
interactive model can use the same tools, but it requires that model's own
credentials and separate behavior evaluation. Do not expose approval/source
import, fixture controls or an unrestricted payment API through an agent toolset.

ADK is the agent framework; A2A is a protocol for communication between agents.
This example does not add an A2A server, Agent Card, remote task lifecycle or
agent marketplace. Add a thin A2A transport only when a buyer's workflow needs
remote delegation, while retaining the same host-owned economic identities.

See the [SDK recovery contract](../../docs/recovery.md),
[security boundaries](../../docs/security-model.md),
[ADK function-tool documentation](https://adk.dev/tools-custom/function-tools/)
and the [checked ADK release](https://github.com/google/adk-python/releases/tag/v2.11.0).
