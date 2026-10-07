# Registry beta launch

Python `haltseal-payments==0.2.0rc2` is published on
[PyPI](https://pypi.org/project/haltseal-payments/0.2.0rc2/).
JavaScript `@haltseal/payments` version `0.2.0-rc.2` is available from the
[GitHub prerelease](https://github.com/HALTSEAL/payments-sdk/releases/tag/v0.2.0-rc.2).
**npm publication is pending.** npm scope ownership still needs to be confirmed
by the account owner before its first registry upload.

## Verified release checkpoint

Checked on 2026-10-07. Python registry availability and the GitHub release files
are verified separately; no npm registry availability is claimed.

| Gate | Result and evidence |
| --- | --- |
| Reviewed preparation | [PR #2](https://github.com/HALTSEAL/payments-sdk/pull/2) merged at `b03f85abd6b7317c77ff6a8d082f4055bf46d61a`; its source tree matches the tested candidate |
| Main SDK checks | [All five jobs passed](https://github.com/HALTSEAL/payments-sdk/actions/runs/37627640111), including installed clients and hosted fixture recovery |
| GitHub release | [`v0.2.0-rc.2`](https://github.com/HALTSEAL/payments-sdk/releases/tag/v0.2.0-rc.2) published from that commit; [release checks and build attestation passed](https://github.com/HALTSEAL/payments-sdk/actions/runs/37627640112) |
| Fresh release downloads | All seven assets matched the published digests; the wheel and tarball also matched the independent rebuild byte for byte |
| Clean release-file installs | Installed Python and Node recovery examples each reproduced six steps, two synthetic dispatches and zero original-lookup redispatches |
| Registry preflight | [Exact-tag rebuild and release-download verification passed](https://github.com/HALTSEAL/payments-sdk/actions/runs/37628225741) with publication disabled |
| GitHub publishing environments | `pypi` and `npm` created with tag-only `v*-rc.*` deployment rules; the workflow also requires the exact released tag in main history |
| Actual PyPI publication | [Attempt 2 passed](https://github.com/HALTSEAL/payments-sdk/actions/runs/37629483057/attempts/2) after the owner registered the matching Trusted Publisher; the release wheel was uploaded with its attestation |
| npm ownership and publication | `@haltseal` scope permission remains unverified; no authenticated initial npm upload was completed |
| Python registry-origin installation | The workflow downloaded the PyPI wheel, matched it byte for byte to the GitHub release, installed it in a fresh virtual environment and reproduced all six hosted fixture steps; two synthetic dispatches, zero original-lookup redispatches |
| JavaScript installation | Verified GitHub release tarball; use the pinned file URL below until an npm upload and registry-origin verification are complete |

The first PyPI attempt was blocked by `invalid-publisher`; the successful second
attempt supersedes that checkpoint. Keep the RC2 tag and release assets unchanged,
and do not upload the already published PyPI version again. Complete npm's first
authenticated upload separately before configuring its Trusted Publisher.

## Current installation paths

Python 3.12+, in a fresh virtual environment:

```sh
python -m pip install haltseal-payments==0.2.0rc2
python -m haltseal_payments_sdk.sandbox --output python-sandbox.json
```

Node 22+, in your project:

```sh
npm install --ignore-scripts --no-audit --no-fund \
  https://github.com/HALTSEAL/payments-sdk/releases/download/v0.2.0-rc.2/haltseal-payments-0.2.0-rc.2.tgz
npx --no-install haltseal-payments-demo --output javascript-sandbox.json
```

The JavaScript import name remains `@haltseal/payments`. Installing a GitHub
tarball with npm does not mean that the package is published in the npm registry.
Both demos use fixed synthetic HTTP fixtures and only their own language runtime.

## What is ready in the repository

- Canonical distributions with the same v2 financial clients and types.
- Python-only and Node-only hosted fixture commands, credential-free records.
- Offline installed-package fault, response, fixture and reproducibility checks.
- A manual registry workflow that uploads the already verified GitHub release bytes.
- Registry download byte checks and an actual hosted exercise after publication.

Only MIT clients and public fixtures are distributed. No private kernel,
provider adapters, issuer keys or customer records are added.

## Registered PyPI publisher

The owner registered this publisher and the first upload created the project.
Maintain it under the existing project's
[Publishing settings](https://pypi.org/manage/project/haltseal-payments/settings/publishing/)
with these exact values:

| Field | Value |
| --- | --- |
| PyPI project | `haltseal-payments` |
| GitHub owner | `HALTSEAL` |
| Repository | `payments-sdk` |
| Workflow filename | `registry.yml` |
| Environment | `pypi` |

No new pending publisher is needed for this existing project. Keep the publishing
account's email verified and 2FA enabled. No PyPI token belongs in this repository,
chat or workflow.

## Owner setup: npm

Confirm control of the npm `@haltseal` scope and access to publish a public
`@haltseal/payments` package. A GitHub organization does not confer npm scope
ownership. Use an npm account with verified email and 2FA.

npm configures a trusted publisher from an existing package's settings. If the
package does not yet exist, the owner must bootstrap its first exact release
from an authenticated local npm session. Download the **released** tarball and
its own checksums, verify them, then publish that tarball:

```sh
npm publish ./haltseal-payments-0.2.0-rc.2.tgz --access public --tag next --ignore-scripts
```

That first manual upload retains the GitHub build attestation but does not claim
npm-generated OIDC provenance. Registry provenance applies to subsequent uploads
through the configured GitHub workflow. Never overwrite an existing version.

In the package settings, configure GitHub Trusted Publishing:

| Field | Value |
| --- | --- |
| Organization/user | `HALTSEAL` |
| Repository | `payments-sdk` |
| Workflow filename | `registry.yml` |
| Environment | `npm` |
| Direct publish | Allowed |

The npm workflow requires npm 11.5.1+ and a supported Node runtime. Node 24 is used.
No npm publishing token is required by the workflow. Configure the publisher
close to its first automated upload; current npm configurations expire if they
are not validated by a successful publish within two days.

## GitHub environments

The `pypi` and `npm` environments exist. Keep their permitted deployment refs aligned with
reviewed release tags. Configure both registry publishers with the matching
workflow filename and environment. Authentication config belongs to the account
owner; the SDK consumers never need publisher accounts.

## Release and verify

1. Merge the reviewed candidate. Existing release automation checks it and creates
   a new GitHub evaluation prerelease; old tags/assets remain unchanged.
2. Run `registry.yml` **from that exact tag**, with its matching `tag` input and
   `publish=false`. The tag must be in main history. This verifies OIDC provenance's
   source commit, checks clients/types, rebuilds and compares the GitHub downloads.
3. For a new version, publish only to registries that have not received that
   version. Set `publish=true` after the matching publisher is configured.
   Never republish the bootstrapped npm version or the existing RC2 PyPI version.
4. Check each fresh registry download against its release bytes and run its
   installed hosted exercise. Advertise each registry independently when verified.

Example using an authenticated GitHub CLI:

```sh
gh workflow run registry.yml --ref v0.2.0-rc.2 -f tag=v0.2.0-rc.2 -f registry=both -f publish=false
# RC2 is already on PyPI. This command is verification only; do not republish it.
```

For a future release, if one upload succeeds and the other fails, keep the published version. Recover
by selecting only the missing registry. An unavailable fixture response pauses
the exercise and does not authorize a financial retry or an automatic new session.

## Package-name migration

Legacy RC4 and SDK v2 RC1 release files retain their original names and bytes.
The registry beta is a new release, not a rename of those archives. Replace the
JavaScript dependency/import with `@haltseal/payments`; Python installs the new
distribution and keeps importing `haltseal_payments_sdk`.

Both Python distributions provide the same import module. Use a fresh virtual
environment or remove the legacy distribution before installing the canonical
one. Do not co-install them. Keep original operation, obligation and attempt
identities with their intended requests through any upgrade.

## Availability statement

The package is an SDK beta for synthetic evaluation. The fixture endpoint and
package provenance do not establish native-provider safety, independent customer
installation, production payment activation or a production SLA.

Official setup references:
[PyPI pending publishers](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/),
[npm trusted publishers](https://docs.npmjs.com/trusted-publishers/).
