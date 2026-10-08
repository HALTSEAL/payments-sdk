# Evaluate your workflow

HALTSEAL Workflow Evaluation Kit 0.1.0 connects two software execution points to
the unchanged SDK, runs a scoped local engine evaluation and gives engineering,
operations and the budget owner the same decision record.

The public adapter starts **unconfigured**. A function that returns an expected
decision without calling the SDK cannot pass. The internal reference adapter
only verifies the kit. It does not prove that customer code was connected.

## Start without a purchase

Install [SDK RC2](../README.md#install), or use the free
[Payment Control Lab](https://github.com/HALTSEAL/payment-control-lab) diagnostics.
The SDK's ordinary terminal demo uses synthetic HTTP fixtures; it does not run
the retained engine. [Request the local evaluator](https://haltseal.com/contact/?topic=payment-api#message)
under the existing scoped evaluation conditions when you are ready. A paid
workflow assessment is optional. The retained engine is separately licensed and
is not included in this public repository or the MIT client distribution.

Clone this repository for the kit examples. The older RC2 source release ZIP
predates these examples. Use the exact source commit supplied with your kit's
`evaluation-manifest.json`. Do not modify the SDK's runtime for a customer.

## What to connect

Copy `examples/workflow-evaluation/workflow.json` and your language's
`customer_adapter` file outside Git. Use non-confidential aliases, not actual
bank account numbers, credentials or customer payment identifiers.

| Hook | Connect to your code | Required behavior |
| --- | --- | --- |
| `map_reference` / `mapReference` | Stable transaction mapping | Both paths return the same agreed business reference |
| `original` | Original software execution point | One SDK create with the retained operation ID, route A and supplied approval |
| `replacement` | Replacement software execution point | One SDK create for route B under the same obligation |
| `recover` | Your lost-reply recovery code | Query the exact retained operation or attempt; never create another payment |
| `stop` | Your application's blocked branch | Return `STOP` on HOLD/REFUSE and perform no further SDK operation |

Call your application's actual functions with the provided client. Route the
evaluated sends through that client; do not make a second direct bank call after
ACCEPT. ACCEPT is a release decision, not proof that a payment settled.
The runner observes calls through the injected SDK only. It cannot discover
hidden senders, direct bank calls, manual portals or omitted application paths.

Complete all hooks, then change `adapter_kind` or `adapterKind` to
`customer-code`. Changing the label alone does not establish coverage. The
report records the operator's declaration, adapter file hash and observed calls;
it does not authenticate every imported application dependency.

The current contract is **synthetic own-account USD 10 local evaluation** with
two software hooks. Supplier, employee and payroll flows, native bank/provider
connections, other paths and production payments need separate qualification.
Use Python 3.12+ or Node.js 22+ and npm on Linux. The scoped bundle installs the
unchanged SDK offline. Discuss application dependencies during setup rather
than silently patching a client or introducing live credentials.

## Check the input and wiring declaration

The JSON input follows [the published schema](../schemas/workflow-evaluation.schema.json).
List your engineering, operations and budget owners, the exact two application
entry-point labels, current controls and excluded paths. These labels remain
declarations until the run observes the corresponding hook calls.

```bash
python examples/workflow-evaluation/python/preflight.py \
  --workflow /tmp/my-workflow.json --adapter /tmp/my-code/adapter.py
```

Preflight is an input/configuration check, not execution evidence. With the empty
template it exits 2 and prints `INCOMPLETE`. `READY_TO_EVALUATE` means the input
and hook exports are configured; an engine campaign still has to complete.
The scoped runner performs the equivalent JavaScript export check.

## Run the supplied scoped evaluator

From the evaluator bundle's root, set `--sdk-checkout` to its pinned
`payments-sdk` directory. In an authorized source checkout, point to the exact
public repository checkout supplied in the manifest.

```bash
python services/payment-api/customer-evaluation/run.py \
  --sdk-checkout ./payments-sdk --workflow /tmp/my-workflow.json \
  --language python --adapter /tmp/my-code/adapter.py \
  --output /tmp/my-haltseal-evaluation
```

For JavaScript, use `--language javascript --adapter /tmp/my-code/adapter.mjs`.
The output directory must be new, private and outside Git. Optional
`--lab-report /tmp/my-lab/report.json` attaches an existing Lab diagnostic by
hash; it remains a separate evidence source and its workflow match requires
owner review. Do not upload customer code, logs or confidential results to the
public repository or the public Workspace forms.

| Local scenario | What the campaign checks |
| --- | --- |
| Original response lost | Lookup retains the original ID; no new original create |
| Original UNKNOWN | Another execution stays HOLD and principal remains reserved |
| Process restart | Original identity and reserved principal are retained |
| Closure with old approval | Replacement remains HOLD |
| Approval signed before closure | Replacement remains HOLD until a fresh postclosure approval |
| Fresh approval and concurrent replacement | One winner among eight contenders; one replacement create |
| Observed PAID and a new path/request ID | Another full-principal payment is REFUSE |

These checks use a real local engine and synthetic loopback provider fixtures.
They do not establish native provider integration, prevented customer incidents,
savings or production readiness.

## Read the result together

| Output | Reader's decision |
| --- | --- |
| `integration-map.html` | Which two declared entry points were observed? |
| `evaluation-report.json` | Which SDK bytes, source pins, calls and scenarios produced this result? |
| `pilot-decision.html` | Retain current controls, evaluate an additional control, or complete the evidence? Who owns the next step? |

All three outputs derive from one run. The HTML includes the JSON record hash;
`SHA256SUMS.txt` binds the output files. HTML is offline, script-free and printable.

`KIT_VERIFIED_REFERENCE_ONLY` means internal fixture wiring completed. It never
becomes customer coverage. `LOCAL_CUSTOMER_HOOKS_EVALUATED` means the declared
customer adapter completed the observed local calls. `INCOMPLETE` or `FAILED`
cannot support a passing conclusion. The owner still reviews current controls,
omitted paths, actual workflow fit and any separate provider conditions.

If a check fails, inspect its **private** stage log, keep the exact operation or
attempt ID, correct the integration and rerun in a fresh output directory. Never
send again just because a reply disappeared, or reuse a prior green report.
An altered source pin or SDK archive is rejected before the engine campaign.

## If a paid pilot is useful

Free public diagnostics and scoped local evaluator requests remain available
independently. The optional [$2,500 Integration Pilot](https://haltseal.com/pilot/start/)
applies the evaluation to one customer workflow and at most two agreed software
paths, with recovery records, remaining conditions, owners and a written next
integration decision. The existing readiness and ten-business-day delivery
conditions and current purchase terms remain in force. A passing synthetic test
does not automatically recommend buying or qualify production deployment.

Keep the non-confidential workflow outline in the
[Workspace](https://haltseal.com/workspace/#workflow). Keep code and generated
private reports local until a separate confidential channel is agreed.
