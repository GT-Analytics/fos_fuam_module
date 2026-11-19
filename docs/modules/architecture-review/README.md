# Fabric Architecture Review in FOS

FAR is a selectable FOS module, included when deploying `all`. It retains FAR's native review pipeline, rule
catalogue, thresholds, scoring, written reports, governance reporting,
workspace-owner reporting, Data Agents and estate ontology. It uses the existing
schema-enabled **FOS_Lakehouse** instead of creating a separate FAR Lakehouse.
The standalone web application (`fabric/app`, including Rayfin) is not included.

**Release status: clean-install and core-pipeline validated; production rollout gated.** A live
SP-authenticated review completed Collect, Analyze, Report and Gold against FOS
evidence. That does not certify a new workspace's permissions, every optional
feature, or restricted-reader isolation. Complete the [production checklist](#production-checklist)
before scheduling or sharing. The `all` selection includes FUAM, FCA and FAR.

## Install

### Prerequisites

- An existing schema-enabled `FOS_Lakehouse` in the target workspace.
- Fabric capacity and tenant settings supporting the selected item types.
  Data Agents and Fabric IQ ontology have their own availability requirements.
- A deployment identity allowed to manage FAR workspace items, publish a Spark
  Environment and create schema `far` and FAR directories.
- Producer pipelines run successfully before enabling their evidence sources.
  Selecting FAR alone does not install or run FUAM or FCA.

### Deploy from FOS

1. Run **Deploy FOS from Repo**, selecting `far` for FAR only, or `all` for
   FUAM, FCA and FAR together. The other choices are `fuam` and `fca`; there is
   no separate FAR checkbox. Existing long module IDs remain accepted by
   scripts and reusable callers. To compose only the two producers
   programmatically, select `fuam,fca`.
2. Wait for **FOS_Install_FAR** to finish. It creates or reuses **FAR_Runtime**,
   imports the packaged requirements, publishes the Environment and verifies
   publication before binding notebooks. First publication can take several
   minutes. No manual package installation is needed.
3. Open **FAR -> Configuration** and configure the Variable Libraries below.
4. Run the first review for one explicit, accessible, non-host workspace.

The installer uses the packaged runtime in `Files/far/runtime/source`; it does
not clone a repository or download another FAR release. FOS stages deployment
archives in session-local temporary storage, not quota-limited notebook
`builtin` resources.

### Configuration

| Item | Purpose |
| --- | --- |
| `FAR_Environment` | FAR review identity, tenant, service principal and Key Vault references. This is a Variable Library, not a Spark Environment. |
| `FAR_Thresholds` | Existing FAR policy, thresholds, scope declarations and capacity profiles. |
| `FAR_Connections` | Independently enable FUAM and FCA evidence; both default off. The `fos` layout resolves this workspace's `FOS_Lakehouse` without manually entering GUIDs. |
| `FAR_Runtime` | Published Spark packages, including `mssql-python` and the pinned Data Agent SDK. Managed by FAR setup; do not use it as a shared custom-package Environment. |

Preserve the existing FAR service principal and Key Vault configuration. Secret
values do not belong in notebook parameters or committed source. Configuration
libraries retain existing values and value sets during upgrades; missing
variables are added with their defaults.

Setup publishes a changed packaged dependency list and reuses an unchanged
published Environment. An ongoing publication or unrelated unpublished library
edits stop setup explicitly. Inspect the Environment before retrying; setup does
not suppress publication failures or alter the workspace's default Environment.

## Workspace folders

Native item names remain unchanged. Setup creates the hierarchy below and moves
only the FAR item IDs it creates or exact configured FAR names it recognizes.

```text
FAR
|-- Deployment
|   `-- FOS_Install_FAR
|-- Configuration
|   |-- FAR_Environment
|   |-- FAR_Thresholds
|   |-- FAR_Connections
|   `-- FAR_Runtime
|-- Pipelines
|   `-- Fabric Arch Review Pipeline
|-- Notebooks
|   `-- FabricArchReview_01_Collect ... FabricArchReview_04_Gold
|-- Governance
|   |-- Governance semantic model and report
|   |-- FabricArchReview_05_Agent and central Data Agent
|   `-- Estate ontology
|-- Workspace Owner
|   |-- Owner semantic model and report
|   |-- FabricArchReview_07_OwnerAccessSync
|   `-- FabricArchReview_08_OwnerAgent and owner Data Agent
`-- Extensions
    |-- FabricArchReview_06_TargetedReviewSetup
    `-- Targeted parent pipeline, Runner and Completion notebooks
```

Optional items appear only when deployed. Rerunning setup or an optional feature
keeps its items in the same subfolders. Existing item IDs and bindings are
preserved. Duplicate configured names, ambiguous folder paths, unsupported
moves and failed move confirmations stop setup rather than silently leaving
items misplaced. `FOS_Lakehouse`, producer items and the common FOS deployment
notebook are never moved.

## Run a review

1. Confirm the selected producer evidence is fresh and the identity checks
   below are complete.
2. Open **FAR -> Pipelines -> Fabric Arch Review Pipeline**.
3. Set `WORKSPACE_IDS` to an explicit comma-separated workspace allow-list.
   **Blank means every eligible workspace the review identity can see**, not
   just this FOS workspace. The FAR host/evidence-source workspace is excluded.
4. Run **Collect -> Analyze -> Report -> Gold**.
5. Inspect collection coverage and findings, not just the pipeline's green
   execution status.

Outputs are persisted in:

- `Files/far/runs/<run-id>/raw/collection_plan.json`: collector outcomes.
- `Files/far/runs/<run-id>/raw/far_evidence.json`: FUAM/FCA source coverage.
- `Files/far/runs/<run-id>/findings.json`: evaluated findings.
- `Files/far/runs/<run-id>/report.md`: the central written review.
- Schema `far`: FAR-owned Gold, evidence and owner-report tables.

The Fabric Report stage writes Markdown. Branded PDF generation is a separate
upstream workstation workflow; Fabric does not silently install Node/Puppeteer.

### Evidence and partial runs

FUAM reads use the FOS `adm` and `capacity_metrics` layouts; FCA reads use `cost`.
Standalone `dbo` connections remain supported by the same readers. Producer
tables are not copied, deduplicated or modified by FAR.

Equivalent repeated context-inventory observations are collapsed to one entity
using their newest modification timestamp. Conflicting contracted values fail
collection. Modification time remains context, not proof of collection freshness.

Missing, stale, unauthorized or incompatible evidence stays an explicit gap.
For example:

- HTTP 401/403 definition or OneLake-role reads can leave a completed pipeline
  with partial collection.
- `no_transfer_snapshot` does not mean there are no publish-to-web or
  organization-wide links.
- FCA capacity-resource enrichment requires an explicit capacity GUID-to-ARM
  mapping in the capacity profiles; an unmapped capacity is not assessed as
  correctly tagged.

Use the collection plan, source coverage and rule results to distinguish
**execution succeeded** from **all required evidence collected**. Never remove
these checks just to make a review appear complete.

## Identities and permissions

FAR has separate permission planes:

1. **Installer identity:** manages FAR items and provisions FAR-owned storage.
2. **Configured FAR service principal:** authenticates review REST and SQL reads.
3. **Notebook execution identity:** reads the staged runtime and writes FAR
   outputs through Spark/OneLake.
4. **Report/Agent consumers:** receive only approved item-scoped access.

Configuring a service principal in `FAR_Environment` does **not** make every
Spark/OneLake operation execute as that service principal. Likewise, Viewer
can be sufficient for the tested SQL evidence reads without allowing every
review API. Diagnose the specific 401/403; do not grant Contributor merely to
fix a read.

Workspace Admin, Member and Contributor roles can already write producer data,
including through inherited group membership. SQL `GRANT SELECT` alone does not
restrict Spark or OneLake.

Before unattended use, have an administrator verify effective permissions with
the actual identities. The reader needs approved source reads; the writer needs
writes only to FAR output tables/directories and read-only access to
`Files/far/runtime`. Do not grant the writer its parent `Files/far`. Prove allowed
FAR writes and denied producer writes using an administrator-provided scratch
canary, never a real producer table. If the boundary cannot be enforced in the
shared Lakehouse, stop and approve an alternative architecture rather than
silently widening access.

See the [OneLake access model](https://learn.microsoft.com/fabric/onelake/security/data-access-control-model).

## Optional FAR features

The installer defaults `DEPLOY_GOLD_REPORT`, `DEPLOY_WORKSPACE_OWNER_REPORT`
and `DEPLOY_ONTOLOGY` to `"true"`. Set an installer parameter to `"false"` to skip
that deployment. These flags do not delete existing items or revoke sharing.
All generated review, owner-sync and targeted helper notebooks inherit
**FAR_Runtime** and the common Lakehouse binding.

### Governance reporting, central Agent and ontology

Run Gold before using the governance report. Run **05_Agent** separately to
publish the central Data Agent; SDK dependencies are already in FAR_Runtime.
Keep central surfaces restricted to reviewers: owner-report RLS does not secure
them. Materialize and validate the estate ontology graph separately in Fabric.
Optional endorsement/label parameters require appropriate tenant permissions.

### Workspace Owner reporting and Agent

Owner sync uses the configured FAR identity for API calls, including semantic-model
refresh. Evidence-reader access alone (workspace Viewer/model Read) is not enough.
Verify that identity's approved refresh permissions on the owner model; HTTP 404
can indicate an inaccessible model as well as a wrong ID. Workspace Contributor
widens write access across FOS, so do not grant it automatically as a read repair.
See the [deployment and identity notes](../../deployment-identity-notes.md#far-owner-sync-refresh-permissions).

Before sharing the owner report:

1. Configure its fixed-identity cloud connection to `FOS_Lakehouse`, with source
   Microsoft Entra SSO disabled, and verify refresh.
2. Run an owner-enabled scoped review through Gold.
3. Run **07_OwnerAccessSync**. Schedule it daily without overlapping manual,
   targeted or other scheduled syncs; grants expire after 24 hours.
4. Approve only item-scoped report/model Read and `WorkspaceOwner` membership.
   Do not grant workspace membership, raw Lakehouse/SQL access, Build or Reshare.
5. Test actual allowed/denied users, expiry, revocation and exports.

Run **08_OwnerAgent** only after successful Gold and access sync. Approve
query-only Agent access, owner-model Read and `WorkspaceOwner` membership.
The owner model is its sole source. Test actual users before sharing.

Recognized older owner-model contracts are upgraded in place while preserving
memberships and connections. Unrecognized security/schema changes stop setup.

### Targeted reviews and Outlook notifications

Run **06_TargetedReviewSetup** with `DEPLOY_TARGETED_REVIEW="true"` after a
successful scoped review. FUAM must be enabled. It provisions the parent,
Runner and Completion notebooks under **Extensions**; it does not run them.
Test with an explicit candidate `WORKSPACE_IDS` allow-list and notifications off.
An empty selection skips FAR; source failures stop the parent.

Email requires a manually approved native Office 365 Outlook connection and an
activated email activity in the parent. Set `FAR_REPORT_URL` to the validated
owner surface, then test delivery before scheduling. Setup sends nothing and
grants no access. Redeployment preserves configured mail wiring but resets the
notification default to false; inspect schedule overrides before resuming.

The full native-feature procedures remain in the
[pinned FAR source](https://github.com/microsoft/fabric-architecture-review/tree/30e91adbed4bb9e6c3793da82ef3e7aaa0eb10ed).
This integration retains its MIT license and notices.

## Upgrade and recovery

- Pause FAR schedules and finish active runs before deploying. Do not upgrade
  the shared runtime underneath a running review.
- Redeploy the same artifact names to retain IDs, configuration, report
  bindings and history. Folder reconciliation runs on every installation.
- An Environment publication failure stops setup before review notebooks are
  deployed. Inspect **FAR_Runtime**, resolve its publish error and rerun.
- Missing-package errors in an existing notebook require the current setup and
  a new Spark session using the published Environment.
- Inspect item-specific 401/403 responses and evidence gaps before changing
  permissions. Broad workspace write grants are not a general repair.
- To roll back, deselect FAR and pause its schedules. Preserve review history
  unless deletion is separately approved. Leave producer data, permissions,
  pipelines and reports untouched.

## Production checklist

- [x] Fresh-workspace installation and same-name redeployment complete.
- [ ] Actual unattended identities can read approved evidence and write FAR
  outputs, but cannot modify producer data or executable runtime.
- [ ] Required collection is complete, or gaps are explicitly accepted.
- [ ] Findings/scoring are compared with stock FAR for equivalent evidence.
- [ ] Selected governance, owner, Agent and ontology surfaces are tested with
  their intended users; restricted consumers cannot reach source data.
- [ ] Required fixed-identity connections, RLS, expiry/revocation and refresh
  are validated before sharing owner surfaces.
- [ ] Schedules run after successful producer refresh and do not overlap access
  syncs; notifications are tested separately before enabling.

Validation on 2026-11-19 included a fresh installation into an empty temporary
workspace and a second deployment preserving item IDs, folder IDs and the
published Environment version. A session using that Environment successfully
imported the SQL driver, Azure identity library and pinned Agent SDK. No review
was started in that workspace, and it was removed after validation.

The separate live pilot verified all four core stages and persisted report/Gold
outputs. It still contained source snapshots, mapping and item-permission gaps;
those must not be described as a complete production review.

## Validate the integration locally

From the repository root, using an environment with `pyyaml`, `requests` and
`python-dotenv` installed:

```powershell
python -m unittest discover -s tests -p "test_*.py"
python cicd\release\compose_release.py --module far --output tmp_deploy\far-release
python cicd\release\compose_release.py --output tmp_deploy\default-release
```

The composer stages the pinned, app-free runtime under `data/far-runtime`, not as
a top-level Fabric item. These checks do not start a scan or validate live
permissions.
