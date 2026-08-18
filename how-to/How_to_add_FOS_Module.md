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

## Workspace folders

`deployment_config.yaml` supports folders at any supported Fabric folder depth. The module must be the first-level folder, with functional folders nested below it:

```yaml
folders:
  - name: Example Module
    folders:
      - name: Deployment
        items:
          - Init_Example.Notebook
      - name: Reporting
        items:
          - Example_SM.SemanticModel
          - Example_Report.Report
      - name: Operations
        folders:
          - name: Daily
            items:
              - Load_Example.DataPipeline
```

Each folder may contain both `items` and child `folders`. Folder names must be unique among siblings, but the same name can be reused beneath different module roots.

## Lakehouse schemas

FOS creates Lakehouses with schema support enabled. Current schema ownership is:

- Admin Monitoring tables use `admin`, except metrics tables.
- Admin Monitoring tables whose names contain `metrics` use `capacity_metrics`.
- Admin Monitoring transient tables use `staging` in `FOS_Lakehouse`.
- Admin Monitoring deployment metadata uses `config` in `FOS_Lakehouse`.
- Cost Analysis tables use `cost` in `FOS_Lakehouse`.
- Direct Lake semantic model partitions declare the corresponding schema name.

When introducing module-specific schemas later, migrate the tables first and then update the corresponding notebook table names, relative Delta paths, pipeline datasets, and semantic model partition `schemaName` values together.

Existing non-schema Lakehouses can't currently be converted in place by Fabric. Deployment validates `properties.defaultSchema` and stops with a migration error if an existing Lakehouse isn't schema-enabled. Create replacement schema-enabled Lakehouses and migrate existing data before updating such a workspace.

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

Run the **Create or Update Feature Branch** workflow with a feature name and choose a deployment scope:

```text
admin-monitoring
cost-analysis
all
```

- If `feature/<name>` does not exist, it is created from `main`.
- If it exists, current `main` is merged into the feature branch and its existing commits are preserved.
- The selected module is passed directly to deployment; other enabled modules in `config/release.yaml` are not deployed.
- `all` deploys every enabled module to the branch workspace.
- The same deployment script runs for creation and update, so existing Fabric items in the feature workspace are updated in place.

The standalone **Deploy FOS from Repo** workflow uses the same dropdown. Reusable workflow callers may still provide a comma-separated `module_ids` value programmatically.