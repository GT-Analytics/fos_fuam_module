# Deployment and identity notes

These notes accompany the [unreleased changes](../CHANGELOG.md). They distinguish
deployment, producer collection and optional FAR owner access; a role that works
for one does not automatically authorize the others.

## Configure your own deployment

Set the target workspace, capacity and Entra security-group object ID in
[`repo_config.yaml`](../cicd/release/repo_config.yaml), and configure the workflow's
required authentication secrets in your own repository. Do not copy another
deployment's identifiers, credentials, Key Vault secrets or notebook outputs.

Select `admin-monitoring`, `cost-analysis`, `far` or `all` in **Deploy FOS from Repo**.
Default/all includes all three modules. Scripts also accept `fuam,fca` to deploy the
producers without FAR. FAR alone requires an existing schema-enabled
`FOS_Lakehouse`.

Deployment imports definitions and performs setup; it does not refresh producer
evidence or start a FAR review. Finish active runs and pause schedules before
upgrading. Existing Lakehouse data is reused; manually edited deployed
notebook/pipeline definitions can be replaced.

## Which identity needs which access?

| Identity or principal | Responsibility | Important distinction |
| --- | --- | --- |
| Deployment identity | Create/update selected workspace items, provision setup and manage required connection role assignments | Its rights are not inherited automatically by every notebook or consumer. |
| Configured `admin_group` | Own the selected API cloud connections | Connection Owner is a connection role, not the workspace Member role. Existing owners and credentials are preserved. |
| FUAM collection identity | Authorized tenant/admin API reads using the selected notebook or Key Vault service-principal mode | Explicit Key Vault mode fails if its configuration is unusable; it does not fall back silently to the user. |
| Configured FAR identity | FAR REST/SQL evidence reads and optional owner-sync API calls | Read-only evidence access is not permission to refresh the owner semantic model. |
| Notebook execution identity | Spark/OneLake runtime reads and output writes | Configuring a FAR service principal does not replace the Spark execution identity. |
| Owner-report consumer | Approved item-scoped report/model access and `WorkspaceOwner` membership | Do not grant workspace membership, raw Lakehouse access, Build or Reshare as a shortcut. |

### Connection ownership and workspace membership

For GitHub Actions deployment, `admin_group` is the Entra security group's
**object ID**, not a client/application ID or display name. Deployment ensures
that group has **Owner** on the API connections used by the selected modules,
including connections found on a rerun. It does not remove existing owners or
replace credentials. Failure to assign the required ownership stops deployment.

Do not treat workspace **Member** as proof that a person owns a cloud connection.
Check the connection itself under **Manage connections and gateways**, and check
workspace roles separately. Direct execution of the deployment notebook can
supply `connection_owner_group` explicitly; an empty value skips this optional
ownership assignment.

## FUAM and FCA first run

1. Deploy the selected modules and wait for setup/initialization to finish.
2. Verify producer authentication, required tenant settings and source access.
3. For FCA, configure the FOCUS storage shortcut in `FOS_Lakehouse` **Files** and
   confirm cost-table initialization completed before the first load.
4. Run the producer pipelines and verify their persisted data before enabling
   their FAR connections.

Public meter/version reference downloads are separate from FOCUS storage and
deployment-repository authentication. A private deployment repository does not
need to become public for these downloads.

## FAR owner-sync refresh permissions

`FabricArchReview_07_OwnerAccessSync` uses the identity selected by
`FAR_Environment` for its API calls. With service-principal mode enabled, the
signed-in notebook user's model permissions do not substitute for that SP's.

Besides approved tenant-admin membership reads, that identity needs permission
to refresh the **workspace-owner semantic model**. Workspace Viewer/model Read
can support evidence reads but is insufficient for this refresh. If sync reports
`Owner model refresh was not accepted: HTTP 404`, verify both the configured
model/workspace IDs and whether the configured identity can access and refresh
that model; a 404 alone does not prove that the model was deleted.

An administrator should choose and validate the approved refresh permissions.
Workspace Contributor can provide write access, but also permits writes beyond
FAR, including producer content. It is not a blanket prerequisite for collecting
evidence or an acceptable substitute for a reviewed least-privilege boundary.
Do not widen workspace roles automatically.

After correcting access, rerun **07_OwnerAccessSync** directly in a fresh session.
A previously successful core review does not need rerunning solely for an
owner-sync permission repair. The sync clears old grants before refreshing,
publishes a replacement snapshot only on successful collection, and refreshes
again. Treat a failed sync as unsuccessful; do not assume old grants were
restored. Grants expire after 24 hours, so schedule non-overlapping daily syncs
and test actual consumers, RLS isolation, expiry and revocation before sharing.

## Public contribution checklist

- Base the contribution on the public fork's current default branch. Publish
  only reviewed source, tests and documentation, not private deployment history.
- Replace deployment-specific settings with clearly configurable examples.
  Exclude credentials, environment identifiers, execution outputs and diagnostics.
- Preserve FAR attribution, license and pinned revision; distinguish packaged
  integration changes from upstream FAR behavior.
- Run the existing release validation and include results in the PR.
- Describe the new default/all behavior and preserve explicit production gates.
  A successful pilot is not a certification of all features or permissions.

See the [FAR operator guide](modules/architecture-review/README.md) for detailed
installation, scope, optional features and production acceptance.
