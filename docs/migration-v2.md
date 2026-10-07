# Upgrade to SDK v2

SDK v2 is `0.2.0rc1` for Python and `0.2.0-rc.1` for Node. Package and import
names remain the same. This version is a separate evaluation release; RC4
downloads and tags are preserved.

1. Retain every unresolved operation, obligation, attempt and intended request.
2. Download the new version and verify its own checksums.
3. Run `python3 tools/check.py` and replay your configured evaluation workflow.
4. Pass the retained obligation to original lookup. Never create a new payment
   identity to work around a contract/deadline error.

| Change | Integration action |
| --- | --- |
| Exact operation echoes required | Upgrade incomplete gateway responses; treat mismatch as uncertainty |
| Complete attempt records required | Supply the typed fields, including nullable evidence fields |
| `OBSERVED` summaries remain supported | Bind the exact attempt and state; read `attempt` for the full record |
| Optional lookup obligation binding | Use the obligation saved before creation |
| Bare blocked lookup decisions | Unbound `HOLD`/`REFUSE` without an attempt may omit an obligation; bound lookup still requires its exact echo |
| Python total deadline | Configure the whole request budget, rather than a per-read idle timeout |
| Python adapters run on SDK workers | Support thread-safe calls; honor the supplied remaining timeout |
| Python default transport connects directly | Provide a reviewed custom transport if your environment requires proxies |
| Original signed JSON string required | Keep issuer text; do not reconstruct it from parsed numeric values |

A timeout can leave an exact original in flight. A cancelled client socket is
not authoritative closure. A fingerprint is correlation, not authorization.

Response guards align with the reviewed Payment API RC5 evaluator contract.
The repository's account-free example still uses the retained fixed RC4 HTTP
fixtures, which supply that response shape. API and SDK versions are separate.

Reviewed runtime hashes, old RC4 hashes and the source contract commit appear
in `release-baseline/v2-migration.json`. Production remains `NO_GO`.
