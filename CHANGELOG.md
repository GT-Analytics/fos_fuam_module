# Changelog

## Unreleased

### Added

- Integrate Fabric Architecture Review (FAR) as a selectable FOS module using
  the schema-enabled `FOS_Lakehouse`, schema `far` and `Files/far/`.
- Package the pinned, MIT-licensed FAR runtime, native review pipeline,
  configuration libraries, governance and workspace-owner reporting, and
  optional Agent, ontology and targeted-review setup.
- Automatically create or reuse and publish `FAR_Runtime`; bind generated
  notebooks to that Environment and the common Lakehouse.
- Organize FAR items into stable, parent-scoped subfolders without moving the
  common Lakehouse or producer items.
- Grant the configured Entra admin group Owner on selected modules' API cloud
  connections, including reused connections, while preserving other owners and
  connection credentials.

### Fixed

- FUAM incremental inventory now uses the selected service-principal or notebook
  identity consistently for Power BI admin requests. Explicit Key Vault
  configuration failures no longer silently fall back to another identity.
  Requests include authorization, timeouts and explicit HTTP failure handling.
- Correct FUAM calendar and version writes to use the `adm` schema.
- Correct FUAM/FCA public version and FCA meter-catalog reference URLs and add
  request timeouts; version requests fail explicitly on HTTP errors.
- Bind FCA initialization to `FOS_Lakehouse` for the combined deployment.
- Stage deployment archives in session-local temporary storage rather than
  quota-limited notebook resources; reuse the shared Lakehouse on redeployment.
- Resolve FAR evidence against the FOS `adm`, `capacity_metrics` and `cost`
  schemas while retaining standalone `dbo` support.
- Collapse repeated, equivalent FUAM evidence observations using their newest
  modification timestamp; conflicting observations still fail collection.

### Changed

- Manual deployment choices retain `admin-monitoring` and `cost-analysis`, with
  `far` and `all`. **Default/all now includes FAR** as well as FUAM and FCA.
  Scripts also accept `fuam`/`fca` aliases, `architecture-review` and
  comma-separated selections; use `fuam,fca` for producers only.
- FAR source connections default off. Enable them only after the selected
  producers have populated fresh evidence.
- Same-name FAR upgrades preserve item IDs, existing configuration and review
  history, but update packaged runtime and deployed notebook/pipeline definitions.

### Upgrade and validation notes

- Review [deployment and identity notes](docs/deployment-identity-notes.md) before
  deployment, especially connection ownership and owner-model refresh access.
- Use an explicit workspace allow-list for the first FAR review. A successful
  pipeline does not establish complete evidence or restricted-reader isolation.
- Automated release tests, isolated clean installation, repeat deployment and
  live core-pipeline execution were validated. Optional feature acceptance,
  effective write isolation, owner RLS/expiry/revocation and evidence completeness
  remain deployment-specific production gates.
- FAR retains its upstream license and notices. Its web application/Rayfin is
  not shipped; PDF generation remains a separate workstation workflow.

See the [FAR operator guide](docs/modules/architecture-review/README.md) for
setup, limitations and the production checklist. These entries are unreleased
contribution notes, not a new numbered upstream release.
