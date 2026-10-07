# Registry beta launch

Candidate: Python `haltseal-payments==0.2.0rc2`, npm
`@haltseal/payments@0.2.0-rc.2`. **Registry publication is pending.** The names and
npm scope ownership must be confirmed by the account owner before release.

## What is ready in the repository

- Canonical distributions with the same v2 financial clients and types.
- Python-only and Node-only hosted fixture commands, credential-free records.
- Offline installed-package fault, response, fixture and reproducibility checks.
- A manual registry workflow that uploads the already verified GitHub release bytes.
- Registry download byte checks and an actual hosted exercise after publication.

Only MIT clients and public fixtures are distributed. No private kernel,
provider adapters, issuer keys or customer records are added.

## Owner setup: PyPI

Use a PyPI account with verified email and 2FA. A paid organization is not required
for this public project. Open [Publishing](https://pypi.org/manage/account/publishing/)
and add a pending GitHub publisher with these values:

| Field | Value |
| --- | --- |
| PyPI project | `haltseal-payments` |
| GitHub owner | `HALTSEAL` |
| Repository | `payments-sdk` |
| Workflow filename | `registry.yml` |
| Environment | `pypi` |

A pending publisher creates the project on first upload; it does not reserve the
name. Confirm name eligibility before announcing it. No PyPI token belongs in
this repository, chat or workflow.

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

Create `pypi` and `npm` environments. Align their permitted deployment refs with
reviewed release tags. Configure both registry publishers with the matching
workflow filename and environment. Authentication config belongs to the account
owner; the SDK consumers never need publisher accounts.

## Release and verify

1. Merge the reviewed candidate. Existing release automation checks it and creates
   a new GitHub evaluation prerelease; old tags/assets remain unchanged.
2. Run `registry.yml` **from that exact tag**, with its matching `tag` input and
   `publish=false`. The tag must be in main history. This verifies OIDC provenance's
   source commit, checks clients/types, rebuilds and compares the GitHub downloads.
3. After registry configuration, run the same workflow from the same tag with
   `publish=true`. Select `pypi` after a manual npm bootstrap, or `both` when both
   publishers already exist. Never republish the bootstrapped npm version.
4. Check the fresh registry downloads against the release bytes and run both
   hosted exercises. Only then label the website commands as available.

Example using an authenticated GitHub CLI:

```sh
gh workflow run registry.yml --ref v0.2.0-rc.2 -f tag=v0.2.0-rc.2 -f registry=both -f publish=false
# After publisher setup; choose the registry that has not already received this version:
gh workflow run registry.yml --ref v0.2.0-rc.2 -f tag=v0.2.0-rc.2 -f registry=pypi -f publish=true
```

If one upload succeeds and the other fails, keep the published version. Recover
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
