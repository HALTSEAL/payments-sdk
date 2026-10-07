# HALTSEAL Payments SDK for JavaScript

Dependency-free ESM client for Node 22+, with TypeScript declarations.
Install the tarball from a [versioned release](https://github.com/HALTSEAL/payments-sdk/releases).
npm registry publication is not claimed.

```js
import {Client, UncertainDispatch} from '@haltseal/payments-evaluation';

// Persist operationId and the intended request before dispatch.
const operationId = 'your-retained-operation-id';
const client = new Client({baseUrl: 'https://your-evaluation-origin.example',
                           apiKey: 'your-evaluation-key'});
try {
  let result;
  try {
    result = await client.createAttempt('your-obligation-id',
      {operationId, route: 'A', approvalRevision: 1});
  } catch (error) {
    if (!(error instanceof UncertainDispatch)) throw error;
    // Lookup failure preserves the hold. It grants no replacement.
    result = await client.lookupOperation(error.operationId);
  }
  // Check decision and execution_outcome before any next step.
} finally { client.close(); }
```

This snippet requires a configured evaluator. Run immediately without one
using `python3 tools/quickstart.py` at the repository root.

Creation uncertainty retains `operationId` and `LOOKUP_OPERATION`.
Resume/cancel/recover uncertainty retains `attemptId` and `LOOKUP_ATTEMPT`.
Read failures retain `REPEAT_READ`. No automatic retry or fallback occurs.
Lookup `404` is not proof of original closure. `error.recovery` is frozen and
JSON serializable, with the Python context's snake_case keys. It omits API
keys and signed source payloads.

`approveSource` requires original JSON text. Do not parse/rewrite signed
nanosecond timestamps with JavaScript numbers. `timeoutMs` bounds fetch and
body consumption. Responses are limited to 1 MiB; redirects are refused.
Injected `fetchImpl` must preserve one send, verified TLS and no redirect/retry.
`onEvent` receives redacted request metadata.

[Recovery](https://github.com/HALTSEAL/payments-sdk/blob/main/docs/recovery.md)
· [API docs](https://haltseal.com/docs/payments/)

`HOLD`/`REFUSE` block the new financial step. `ACCEPT` is not proof of payment.
Production remains `NO_GO`. MIT licensed client only.
