# What this release establishes

SDK v2 adds exact identity/record validation and total caller deadlines to
the two public MIT clients. Installed-package checks run a shared HTTP fault
matrix, independent valid/corrupt response records, the recovery example,
bounded Python transport tests and byte-identical clean builds through an
explicit public file allowlist. Old RC4 archives remain unchanged; the reviewed
runtime upgrade is pinned in `release-baseline/v2-migration.json`.

They do **not** establish native-provider behavior, independent kernel
operation, customer deployment, production readiness or exactly-once delivery
across arbitrary systems. Workflow qualification is a separate step.

## Provenance

Original public RC4 packages are retained under `release-baseline/`, pinned
in `provenance.json`. Fixture files come from the public SDK sandbox `1.0.0`
with its MIT notice retained. No private service history is imported.

The kernel, native adapters, issuer keys, internal specifications, private
qualification reports and customer records are excluded. MIT applies only
to the published clients and fixtures.

## Releases

Run `python3 tools/check.py`. The offline builder reads the explicit
`tools/release-files.json` allowlist and emits packages, a deterministic source
bundle, `manifest.json` and `SHA256SUMS.txt`. Each release has its own checksums.

The Release workflow validates matching package versions, reruns checks and
publishes those exact artifacts as a prerelease after version changes on main.
Manual releases must also run from main. Release artifacts receive a GitHub
build-provenance attestation, attached as `build-attestation.jsonl`. Existing tags/assets are preserved;
repeat automatic events skip an already published version, while an explicit
manual overwrite request fails. Registry publication is a separate step.
