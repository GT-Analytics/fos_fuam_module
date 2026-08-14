import argparse
import json
import os
import shutil
import uuid
from pathlib import Path

import yaml


UUID_NAMESPACE = uuid.NAMESPACE_DNS
UUID_PREFIX = "FOS"


class CompositionError(ValueError):
    pass


def _load_yaml(path):
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def _load_json(path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _copy_tree(source, target, owners, module_id, excluded_names=None):
    excluded_names = excluded_names or set()
    for source_file in source.rglob("*"):
        if not source_file.is_file() or source_file.name in excluded_names:
            continue
        relative_path = source_file.relative_to(source)
        target_file = target / relative_path
        owner = owners.get(relative_path)
        if owner is not None:
            if source_file.read_bytes() != target_file.read_bytes():
                raise CompositionError(
                    f"Modules '{owner}' and '{module_id}' provide different "
                    f"content for '{relative_path.as_posix()}'"
                )
            continue
        target_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, target_file)
        owners[relative_path] = module_id


def _register_source_items(source, owners, module_id):
    for item_path in source.iterdir():
        if not item_path.is_dir():
            continue
        existing_owner = owners.get(item_path.name)
        if existing_owner is not None:
            raise CompositionError(
                f"Modules '{existing_owner}' and '{module_id}' both provide "
                f"source item '{item_path.name}'"
            )
        owners[item_path.name] = module_id


def _merge_named_values(target, incoming, module_id, config_key):
    for name, value in incoming.items():
        existing = target.get(name)
        if existing is not None and existing != value:
            raise CompositionError(
                f"Module '{module_id}' has a conflicting '{config_key}.{name}'"
            )
        target[name] = value


def _merge_deployment_config(composed, incoming, module_id):
    if not composed:
        composed = {
            "workspace": incoming.get("workspace"),
            "connections": {},
            "connection_specs": {},
            "semantic_model_lakehouses": {},
            "post_deployment": {
                "jobs": [],
                "sql_endpoints": [],
            },
            "folders": [],
        }

    if composed.get("workspace") != incoming.get("workspace"):
        raise CompositionError(
            f"Module '{module_id}' has a conflicting deployment_config 'workspace'"
        )

    _merge_named_values(
        composed["connections"], incoming.get("connections", {}), module_id, "connections"
    )
    _merge_named_values(
        composed["connection_specs"],
        incoming.get("connection_specs", {}),
        module_id,
        "connection_specs",
    )
    _merge_named_values(
        composed["semantic_model_lakehouses"],
        incoming.get("semantic_model_lakehouses", {}),
        module_id,
        "semantic_model_lakehouses",
    )

    post_deployment = incoming.get("post_deployment", {})
    for key in ("jobs", "sql_endpoints"):
        for value in post_deployment.get(key, []):
            if value not in composed["post_deployment"][key]:
                composed["post_deployment"][key].append(value)

    folders_by_name = {folder["name"]: folder for folder in composed["folders"]}
    for folder in incoming.get("folders", []):
        target = folders_by_name.get(folder["name"])
        if target is None:
            target = {"name": folder["name"], "items": []}
            composed["folders"].append(target)
            folders_by_name[folder["name"]] = target
        for item in folder.get("items", []):
            if item not in target["items"]:
                target["items"].append(item)

    return composed


def _merge_deployment_order(composed, incoming, module_id):
    items_by_name = {item["name"]: item for item in composed}
    for item in incoming:
        name = item["name"]
        expected_id = str(uuid.uuid3(UUID_NAMESPACE, UUID_PREFIX + name))
        if item.get("fos_id") != expected_id:
            raise CompositionError(
                f"Module '{module_id}' has an invalid fos_id for '{name}': "
                f"expected '{expected_id}'"
            )
        existing = items_by_name.get(name)
        if existing is not None:
            if existing != item:
                raise CompositionError(
                    f"Module '{module_id}' defines conflicting deployment metadata "
                    f"for '{name}'"
                )
            continue
        composed.append(item)
        items_by_name[name] = item


def _validate_module_contract(
    module_id, manifest, deployment_config, deployment_order, src_dir
):
    order_names = {item["name"] for item in deployment_order}
    source_names = {path.name for path in src_dir.iterdir() if path.is_dir()}
    missing_source_entries = source_names - order_names
    if missing_source_entries:
        raise CompositionError(
            f"Module '{module_id}' source items are missing from deployment_order.json: "
            f"{sorted(missing_source_entries)}"
        )

    connections = deployment_config.get("connections", {})
    connection_specs = deployment_config.get("connection_specs", {})
    if set(connections) != set(connection_specs):
        raise CompositionError(
            f"Module '{module_id}' must define one connection_specs entry for every connection"
        )
    missing_connection_entries = set(connections.values()) - order_names
    if missing_connection_entries:
        raise CompositionError(
            f"Module '{module_id}' connections are missing from deployment_order.json: "
            f"{sorted(missing_connection_entries)}"
        )

    semantic_targets = deployment_config.get("semantic_model_lakehouses", {})
    missing_models = set(semantic_targets) - source_names
    missing_lakehouses = set(semantic_targets.values()) - order_names
    if missing_models or missing_lakehouses:
        raise CompositionError(
            f"Module '{module_id}' has invalid semantic model targets: "
            f"models={sorted(missing_models)}, lakehouses={sorted(missing_lakehouses)}"
        )

    post_deployment = deployment_config.get("post_deployment", {})
    post_jobs = {job["item"] for job in post_deployment.get("jobs", [])}
    missing_jobs = post_jobs - source_names
    missing_endpoints = set(post_deployment.get("sql_endpoints", [])) - order_names
    if missing_jobs or missing_endpoints:
        raise CompositionError(
            f"Module '{module_id}' has invalid post-deployment references: "
            f"jobs={sorted(missing_jobs)}, sql_endpoints={sorted(missing_endpoints)}"
        )

    provided_resources = set(manifest.get("shared_resources", {}).get("provides", []))
    missing_resources = provided_resources - order_names
    if missing_resources:
        raise CompositionError(
            f"Module '{module_id}' provided resources are missing from deployment_order.json: "
            f"{sorted(missing_resources)}"
        )


def normalize_selected_modules(selected_modules):
    if selected_modules is None:
        return None
    if isinstance(selected_modules, str):
        modules = [value.strip() for value in selected_modules.split(",") if value.strip()]
    else:
        modules = [str(value).strip() for value in selected_modules if str(value).strip()]
    if not modules or modules == ["all"]:
        return None
    if "all" in modules:
        raise CompositionError("'all' cannot be combined with individual module IDs")
    return list(dict.fromkeys(modules))


def _select_modules(repo_root, declared_modules, selected_modules):
    modules_by_id = {module["id"]: module for module in declared_modules}
    if selected_modules is None:
        selected_ids = {
            module["id"] for module in declared_modules if module.get("enabled", True)
        }
    else:
        selected_ids = set(selected_modules)
        unknown_ids = selected_ids - set(modules_by_id)
        if unknown_ids:
            raise CompositionError(f"Unknown selected modules: {sorted(unknown_ids)}")

        pending = list(selected_ids)
        while pending:
            module_id = pending.pop()
            manifest = _load_yaml(
                repo_root / "config" / "modules" / module_id / "module.yaml"
            )
            for dependency in manifest.get("dependencies", []):
                if dependency not in modules_by_id:
                    raise CompositionError(
                        f"Module '{module_id}' declares unknown dependency '{dependency}'"
                    )
                if dependency not in selected_ids:
                    selected_ids.add(dependency)
                    pending.append(dependency)

    return sorted(
        (modules_by_id[module_id] for module_id in selected_ids),
        key=lambda module: (module.get("order", 0), module["id"]),
    )


def compose_release(repo_root, output_root, selected_modules=None):
    repo_root = Path(repo_root).resolve()
    output_root = Path(output_root).resolve()
    release_config = _load_yaml(repo_root / "config" / "release.yaml")
    if release_config.get("schema_version") != 1:
        raise CompositionError("config/release.yaml must use schema_version 1")

    if selected_modules is None:
        selected_modules = os.environ.get("FOS_MODULE_IDS")
    selected_modules = normalize_selected_modules(selected_modules)

    declared_modules = release_config.get("modules", [])
    declared_ids = {module["id"] for module in declared_modules}
    config_modules_dir = repo_root / "config" / "modules"
    available_ids = {
        path.name for path in config_modules_dir.iterdir() if path.is_dir()
    }
    undeclared_ids = available_ids - declared_ids
    if undeclared_ids:
        raise CompositionError(
            f"Module payloads are not declared in config/release.yaml: "
            f"{sorted(undeclared_ids)}"
        )
    enabled_modules = _select_modules(repo_root, declared_modules, selected_modules)
    if not enabled_modules:
        raise CompositionError("config/release.yaml does not enable any modules")

    output_root.mkdir(parents=True, exist_ok=True)
    output_config = output_root / "config"
    output_data = output_root / "data"
    output_src = output_root / "src"
    for path in (output_config, output_data, output_src):
        path.mkdir(parents=True, exist_ok=True)

    deployment_config = {}
    deployment_order = []
    data_owners = {}
    src_owners = {}
    source_item_owners = {}
    shared_resource_owners = {}
    enabled_ids = {module["id"] for module in enabled_modules}

    for module in enabled_modules:
        module_id = module["id"]
        config_dir = repo_root / "config" / "modules" / module_id
        data_dir = repo_root / "data" / "modules" / module_id
        src_dir = repo_root / "src" / "modules" / module_id
        manifest = _load_yaml(config_dir / "module.yaml")

        if manifest.get("schema_version") != 1 or manifest.get("id") != module_id:
            raise CompositionError(
                f"Module '{module_id}' must have a matching schema_version 1 module.yaml"
            )
        missing_dependencies = set(manifest.get("dependencies", [])) - enabled_ids
        if missing_dependencies:
            raise CompositionError(
                f"Module '{module_id}' is missing dependencies: "
                f"{sorted(missing_dependencies)}"
            )

        for resource in manifest.get("shared_resources", {}).get("provides", []):
            existing_owner = shared_resource_owners.get(resource)
            if existing_owner is not None:
                raise CompositionError(
                    f"Modules '{existing_owner}' and '{module_id}' both provide "
                    f"shared resource '{resource}'"
                )
            shared_resource_owners[resource] = module_id

        module_deployment_config = _load_yaml(
            config_dir / "deployment_config.yaml"
        )
        module_deployment_order = _load_json(config_dir / "deployment_order.json")
        _validate_module_contract(
            module_id,
            manifest,
            module_deployment_config,
            module_deployment_order,
            src_dir,
        )
        deployment_config = _merge_deployment_config(
            deployment_config,
            module_deployment_config,
            module_id,
        )
        _merge_deployment_order(
            deployment_order,
            module_deployment_order,
            module_id,
        )
        _copy_tree(
            data_dir,
            output_data,
            data_owners,
            module_id,
            excluded_names={path.name for path in data_dir.glob("current_*_version.json")},
        )
        _register_source_items(src_dir, source_item_owners, module_id)
        _copy_tree(src_dir, output_src, src_owners, module_id)

    with (output_config / "deployment_config.yaml").open("w", encoding="utf-8") as file:
        yaml.safe_dump(deployment_config, file, sort_keys=False, allow_unicode=True)
    with (output_config / "deployment_order.json").open("w", encoding="utf-8") as file:
        json.dump(deployment_order, file, indent=4)

    return {
        "modules": [module["id"] for module in enabled_modules],
        "items": len(deployment_order),
        "source_items": len(source_item_owners),
        "data_files": len(data_owners),
    }


def main():
    parser = argparse.ArgumentParser(description="Compose enabled FOS modules")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).parents[2])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--module",
        action="append",
        dest="modules",
        help="Compose only this module and its dependencies; repeat for multiple modules",
    )
    args = parser.parse_args()
    summary = compose_release(args.repo_root, args.output, selected_modules=args.modules)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()