HALTSEAL Payments SDK v2: exact-original responses and total caller deadlines.

`0.2.0-rc.1` requires matching operation/obligation identities, validates complete
attempt records and preserves recovery context on malformed or late responses.
Python uses a bounded one-send transport with a total caller deadline. Original
signed source JSON text is retained in both clients. RC4 archives are preserved;
the reviewed runtime migration and this release's checksums identify the new code.

Run `python3 tools/quickstart.py` from the source bundle for the synthetic
original-recovery example in both installed clients. Run `python3 tools/check.py`
for shared HTTP faults, response identity/record cases, recovery parity and clean-build
reproducibility. The attached verification.json records the checks.

Evaluation only. Synthetic fixtures, no real funds, no native-provider or
retained-kernel qualification. Production remains NO_GO.

API docs: https://haltseal.com/docs/payments/
Browser sandbox: https://haltseal.com/sandbox/
Workflow pilot: https://haltseal.com/pricing/#workflow
