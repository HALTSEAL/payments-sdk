# HALTSEAL Payments SDK for Python

Dependency-free client for Python 3.12+. Install the wheel from a
[versioned release](https://github.com/HALTSEAL/payments-sdk/releases).
PyPI publication is not claimed.

```python
from haltseal_payments_sdk import Client, UncertainDispatch

# Persist operation_id with the intended request before dispatch.
operation_id = "your-retained-operation-id"
with Client("https://your-evaluation-origin.example", "your-evaluation-key") as client:
    try:
        result = client.create_attempt("your-obligation-id", operation_id=operation_id,
                                       route="A", approval_revision=1)
    except UncertainDispatch as error:
        # Lookup failure preserves the hold. It grants no replacement.
        result = client.lookup_operation(error.operation_id)
    # Check decision and execution_outcome before any next step.
```

This snippet requires a configured evaluator. To run immediately without one,
use `python3 tools/quickstart.py` at the repository root.

Creation uncertainty retains `operation_id` and `LOOKUP_OPERATION`.
Resume/cancel/recover uncertainty retains `attempt_id` and `LOOKUP_ATTEMPT`.
Read failures retain `REPEAT_READ`. No automatic retry or fallback occurs.
Lookup `404` is not proof of original closure. Recovery context is immutable
and JSON serializable, without the API key or signed source payload.

`approve_source` requires original signed JSON text. Do not rewrite it.
Custom transports must preserve one send, verified TLS and refused redirects.
Event callbacks receive redacted request metadata.

[Recovery](https://github.com/HALTSEAL/payments-sdk/blob/main/docs/recovery.md)
· [API docs](https://haltseal.com/docs/payments/)

`HOLD`/`REFUSE` block the new financial step. `ACCEPT` is not proof of payment.
Production remains `NO_GO`. MIT licensed client only.
