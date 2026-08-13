# Add a FOS Module

FOS modules are developed independently and synchronized into isolated paths in the release repository. Every module uses the same file schemas and differs only by its module directory.

## Required structure

Replace `<module-id>` with a stable lowercase identifier:

```text
cicd/modules/<module-id>/
  item_src_config.yaml
  fos_get_ressources.py
config/modules/<module-id>/
  module.yaml
  deployment_config.yaml
  deployment_order.json
data/modules/<module-id>/
  current_fos_version.json
  ...
src/modules/<module-id>/
  <Fabric item folders>
```

The release repository owns these shared files:

```text
cicd/release/
config/release.yaml
scripts/Deploy_FOS.ipynb
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
cicd/modules/<module-id>
config/modules/<module-id>
data/modules/<module-id>
src/modules/<module-id>
```

Other modules and release-owned files are not modified.

`current_fos_version.json` is module release metadata and is not copied into the temporary deployment payload. Other data filenames must be unique across modules unless their contents are identical.

## Validation

Run validation before publishing:

```powershell
python -m unittest discover -s tests -p 'test_*.py'
python cicd/release/compose_release.py --output "$env:TEMP/fos-release"
```

Composition fails for duplicate item names, invalid FOS IDs, missing dependencies, conflicting shared-resource ownership, inconsistent global configuration, or undeclared module payloads.