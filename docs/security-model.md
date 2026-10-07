# Client security boundaries

These clients protect the integration boundary. They validate evidence shapes
and preserve original identity when replies are unavailable. Payment authority
and authoritative predecessor closure belong to the connected evaluator/kernel.

| Property | V2 behavior and evidence |
| --- | --- |
| Exact request identity | Creation/lookup echo checks; optional retained obligation binding |
| Complete original record | Typed identity, amount, route, state, revision and evidence fields checked |
| Cross-record consistency | Nested identities, principal, approval and duplicate attempt checks |
| One send | Shared HTTP counters detect resends and redirects |
| Total caller deadline | Slowly arriving headers, fixed/chunked/close-delimited transport cases |
| Resource bounds | 16 KiB requests, 1 MiB responses; at most 64 Python transport workers per process |
| Recovery evidence | Immutable serializable context; API keys and signed source bodies omitted |
| Cleanup | Primary uncertainty retained if custom cleanup fails |
| Release integrity | Preserved baseline, reviewed hashes, deterministic builds, checksums and GitHub build-provenance attestation |

The default transports verify HTTPS and refuse redirects. Literal loopback
HTTP is permitted for local evaluation. Python connects directly. Custom
transports must preserve TLS, one send, response limits and no redirects/retries.
Event callbacks must return promptly and handle only redacted request metadata.

Deadline expiry cannot retract a request already accepted by a server. Python
interrupts default sockets and bounds worker count; an uninterruptible resolver
or custom adapter may finish later. Node cancellation also depends on adapter
cooperation. The SDK rejects late results and retains the original context.

The synthetic tests establish client behavior, not bank/provider closure,
customer installation, arbitrary exactly-once delivery or production readiness.
Checksums verify artifact bytes, not payment authorization. The kernel,
issuer keys, native adapters and customer records are excluded.

Report vulnerabilities privately through [SECURITY.md](../SECURITY.md).
