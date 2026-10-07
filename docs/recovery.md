# Recover the exact original

Persist an operation ID and intended request before a modifying call. A missing
reply can mean the original committed. It grants no new send or route change.

| Python | JavaScript | If the reply is uncertain |
| --- | --- | --- |
| `create_attempt` | `createAttempt` | `LOOKUP_OPERATION`: look up the same operation ID |
| `resume`, `cancel`, `recover` | `resume`, `cancel`, `recover` | `LOOKUP_ATTEMPT`: read the same `attempt` |
| `approve_source` | `approveSource` | `REVIEW_SOURCE`: review the signed source import |
| `obligation`, `attempt`, `lookup_operation` | `obligation`, `attempt`, `lookupOperation` | `REPEAT_READ`: repeat the read according to application policy |

The client never performs the next action automatically. Keep unresolved work
blocked across restarts. Lookup `404` does not establish that the original
never executed or that its principal is available.

## Errors retain evidence

| Error | Meaning | Response |
| --- | --- | --- |
| `ValidationError` | Invocation rejected locally | Correct input before sending |
| `APIError` | Recognized API error received | Review code/context; do not infer closure |
| `UncertainDispatch` | Modifying request may have executed | Retain identity; follow lookup/review action |
| `TransportError` on a read | Read unavailable or invalid | Preserve hold; repeat read according to policy |

Timeouts, connection loss, `408`, `429`, `5xx`, modifying redirects and invalid
response contracts can leave a modifying call uncertain. Retry middleware
must not turn those failures into another financial send.

The recovery context contains `api_origin`, `request_kind`, `action`,
`identity_kind`, `identity_value`, `request_fingerprint`, `operation_id`,
`attempt_id`, `obligation_id`, `approval_revision` and
`request_may_have_executed`. Python has `error.recovery.to_dict()`;
JavaScript has `error.recovery`. Both are immutable and serializable and omit
the API key and signed payload. Redact customer identifiers before sharing.

## Decisions and observations

`HOLD`/`REFUSE` block the new financial step. `ACCEPT` alone does not prove
payment. Read the execution outcome and exact original evidence before a
replacement decision. The example injects closure and approval through test
fixture endpoints; those endpoints establish no real-world closure.

## Transport boundary

Default clients send once, refuse redirects, limit response size and validate
the evaluation response shape. Use HTTPS or literal loopback HTTP origins,
without a path, query or embedded credentials. Keep TLS verification enabled.
Injected transports must preserve these guarantees and never retry internally.

Signed source imports use original JSON text. Do not normalize signatures or
rewrite timestamps. `close()` prevents new calls; custom transport owners
close their resources according to the documented interface.

[Compatibility](compatibility.md) · [Release scope](release-scope.md)
