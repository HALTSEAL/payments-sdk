# What this release establishes

The two public MIT RC4 clients now have reviewable source, runnable recovery
examples and package-level checks. Checks establish runtime/type equality
with public RC4, installed-package behavior on synthetic HTTP fixtures,
one-send recovery handling across a shared failure matrix and byte-identical
clean builds using an explicit public file allowlist.

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

The Release workflow validates the requested tag, reruns checks and publishes
those exact artifacts as a prerelease. It refuses to overwrite an existing
release or tag. Registry publication is a separate step.
