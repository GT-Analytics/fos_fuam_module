# Add a FOS Module

FOS modules are developed independently and synchronized into isolated paths in the release repository. Every module uses the same file schemas and differs only by its module directory.

## Required structure

Replace `<module-id>` with a stable lowercase identifier:

```text
cicd/modules/<module-id>/
  item_src_config.yaml
config/modules/<module-id>/
  module.yaml
  deployment_config.yaml
  deployment_order.json
data/modules/<module-id>/
  current_<module>_version.json
  ...
src/modules/<module-id>/
  <Fabric item folders>
docs/modules/<module-id>/
  ...
```

The release repository owns these shared files:

```text
cicd/release/
config/release.yaml
scripts/Deploy_FOS.ipynb
```

Module development repositories also contain the shared exporter:

```text
cicd/export_module.py
```

## Release configuration

Add the module to `config/release.yaml`:

```yaml
modules:
  - id: <module-id>
    enabled: true
    order: 20
```

Declare module metadata and dependencies in `config/modules/<module-id>/module.yaml`:

```yaml
schema_version: 1
id: <module-id>
display_name: Example Module
version: 1.0.0
dependencies:
  - admin-monitoring
```

## Deterministic IDs

All modules use the overarching FOS namespace. IDs must be generated from the Fabric item name only:

```python
uuid.uuid3(uuid.NAMESPACE_DNS, "FOS" + item_name)
```

The module ID must not be included in UUID generation. Fabric item names must therefore be unique across enabled modules.

## Synchronization

Set `MODULE_ID` in both module sync workflows. Synchronization replaces only these paths in the destination repository:

```text
config/modules/<module-id>
data/modules/<module-id>
src/modules/<module-id>
docs/modules/<module-id>  # optional
```

The exporter and `item_src_config.yaml` remain development-only and are not synchronized. Other modules and release-owned files are not modified.

Refresh a module's exported Fabric items with:

```powershell
python cicd/export_module.py --module <module-id>
```

`current_fos_version.json` is module release metadata and is not copied into the temporary deployment payload. Other data filenames must be unique across modules unless their contents are identical.

## Validation

Run validation before publishing:

```powershell
python -m unittest discover -s tests -p 'test_*.py'
python cicd/release/compose_release.py --output "$env:TEMP/fos-release"
```

Composition fails for duplicate item names, invalid FOS IDs, missing dependencies, conflicting shared-resource ownership, inconsistent global configuration, or undeclared module payloads.

## Feature branch deployment

Run the **Create or Update Feature Branch** workflow with a feature name and module ID.

- If `feature/<name>` does not exist, it is created from `main`.
- If it exists, current `main` is merged into the feature branch and its existing commits are preserved.
- The selected module is passed directly to deployment; other enabled modules in `config/release.yaml` are not deployed.
- The same deployment script runs for creation and update, so existing Fabric items in the feature workspace are updated in place.

The standalone **Deploy FOS from Repo** workflow supports `all`, `admin-monitoring`, and `cost-analysis`. Select `all` only for a complete combined deployment.