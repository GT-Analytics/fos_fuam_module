import ast
import json
import os
import shutil
import tempfile
import unittest
import uuid
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

from cicd.release.compose_release import (
    CompositionError,
    compose_release,
    normalize_selected_modules,
)


class ComposeReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_airgapped_notebook_stages_and_reads_files_outside_resources(self):
        repo = Path(__file__).resolve().parents[1]
        notebook = json.loads((repo / "scripts/Deploy_FOS.ipynb").read_text(encoding="utf-8"))
        cells = ["".join(cell["source"]) for cell in notebook["cells"]
                 if cell["cell_type"] == "code"]
        staging = next(cell for cell in cells if "def copy_deployment_files_from_lakehouse(" in cell)
        definitions = ast.Module(
            body=[node for node in ast.parse(staging).body
                  if isinstance(node, (ast.FunctionDef, ast.Assign))],
            type_ignores=[],
        )
        archives = self.root / "archives"
        archives.mkdir()
        payloads = {
            "src.zip": {"src/Example.Notebook/notebook-content.ipynb": "{}"},
            "config.zip": {"config/deployment_config.yaml": "workspace: FOS"},
            "data.zip": {"data/far-runtime/orchestration/setup.py": "# runtime"},
        }
        for name, files in payloads.items():
            with zipfile.ZipFile(archives / name, "w") as archive:
                for path, content in files.items():
                    archive.writestr(path, content)

        def copy(source, destination):
            target = Path(destination.removeprefix("file:"))
            self.assertTrue(target.is_relative_to(Path(tempfile.gettempdir())))
            self.assertNotIn("builtin", target.parts)
            shutil.copyfile(archives / source.rsplit("/", 1)[1], target)

        scope = dict(tempfile=tempfile, Path=Path, os=os, shutil=shutil, zipfile=zipfile,
                     ZipFile=zipfile.ZipFile, fabric=SimpleNamespace(get_notebook_workspace_id=lambda: "ws"),
                     notebookutils=SimpleNamespace(fs=SimpleNamespace(
                         ls=lambda _: [SimpleNamespace(name=name) for name in payloads], cp=copy)))
        exec(compile(definitions, "<deployment-staging>", "exec"), scope)
        self.addCleanup(scope["deployment_workspace"].cleanup)
        scope["_resolve_lakehouse_id"] = lambda *_: "lh"
        scope["copy_deployment_files_from_lakehouse"]("LH_Temp")
        root = scope["deployment_root"]
        self.assertEqual((root / "config/deployment_config.yaml").read_text(), "workspace: FOS")
        self.assertTrue((root / "data/far-runtime/orchestration/setup.py").is_file())
        self.assertFalse((root / "data.zip").exists())
        helpers = next(cell for cell in cells if "def copy_to_tmp(" in cell)
        reader = next(node for node in ast.parse(helpers).body
                      if isinstance(node, ast.FunctionDef) and node.name == "copy_to_tmp")
        exec(compile(ast.Module(body=[reader], type_ignores=[]), "<deployment-reader>", "exec"), scope)
        self.assertEqual(scope["copy_to_tmp"]("Example.Notebook"),
                         {"src/Example.Notebook/notebook-content.ipynb": b"{}"})
        (root / "data/stale.txt").write_text("old release")
        scope["copy_deployment_files_from_lakehouse"]("LH_Temp")
        self.assertFalse((root / "data/stale.txt").exists())

    def test_far_only_installs_into_existing_lakehouse(self):
        repo = Path(__file__).resolve().parents[1]
        module = "architecture-review"
        default_output = self.root / "default"
        default_summary = compose_release(repo, default_output, selected_modules="fuam,fca")
        self.assertEqual(default_summary["modules"], ["admin-monitoring", "cost-analysis"])
        self.assertFalse((default_output / "data/far-runtime").exists())
        output = self.root / "far"
        summary = compose_release(repo, output, selected_modules=module)
        self.assertEqual(summary["modules"], [module])
        self.assertEqual(summary["source_items"], 1)
        config = yaml.safe_load((output / "config/deployment_config.yaml").read_text())
        self.assertEqual(config["existing_lakehouses"], ["FOS_Lakehouse.Lakehouse"])
        self.assertEqual(config["post_deployment"]["jobs"], [{"item": "FOS_Install_FAR.Notebook"}])
        installer = output / "src/FOS_Install_FAR.Notebook/notebook-content.ipynb"
        metadata = json.loads(installer.read_text(encoding="utf-8"))["metadata"]
        self.assertEqual(metadata["dependencies"]["lakehouse"]["default_lakehouse_name"], "FOS_Lakehouse")
        runtime = output / "data" / "far-runtime"
        for path in (
            "LICENSE.TXT",
            "config/sources.yaml",
            "fabric/notebooks/01_collect.ipynb",
            "reports/ontology/ontology.py",
        ):
            self.assertTrue((runtime / path).is_file(), path)
        self.assertFalse((runtime / "fabric/app").exists())
        self.assertFalse((runtime / "reports/app_contract.py").exists())
        self.assertFalse((output / "src/far-runtime").exists())

    def test_all_includes_all_three_and_aliases_preserve_single_selection(self):
        repo = Path(__file__).resolve().parents[1]
        summary = compose_release(repo, self.root / "combined", selected_modules="all")
        self.assertEqual(summary["modules"], ["admin-monitoring", "cost-analysis", "architecture-review"])
        config = yaml.safe_load((self.root / "combined/config/deployment_config.yaml").read_text())
        self.assertNotIn("existing_lakehouses", config)
        self.assertIn("far", config["lakehouse_schemas"]["FOS_Lakehouse.Lakehouse"])
        summary = compose_release(repo, self.root / "single", selected_modules="far")
        self.assertEqual(summary["modules"], ["architecture-review"])
        summary = compose_release(repo, self.root / "default")
        self.assertEqual(summary["modules"], ["admin-monitoring", "cost-analysis", "architecture-review"])
        self.assertEqual(normalize_selected_modules("fuam,fca,far,architecture-review"),
                         ["admin-monitoring", "cost-analysis", "architecture-review"])

    def test_workflow_exposes_four_choices_without_an_extra_far_switch(self):
        repo = Path(__file__).resolve().parents[1]
        # PyYAML's YAML 1.1 loader interprets the GitHub Actions key "on" as True.
        workflow = yaml.safe_load((repo / ".github/workflows/deploy-fos-from-repo.yml").read_text(encoding="utf-8"))
        triggers = workflow.get("on", workflow.get(True))
        manual = triggers["workflow_dispatch"]["inputs"]
        self.assertEqual(manual["module_id"]["options"], ["fuam", "fca", "far", "all"])
        self.assertNotIn("include_far", manual)
        self.assertNotIn("include_far", triggers["workflow_call"]["inputs"])
        self.assertNotIn("FOS_INCLUDE_FAR", workflow["env"])

    def add_module(self, module_id, item_name, source_content="content"):
        config_dir = self.root / "config" / "modules" / module_id
        data_dir = self.root / "data" / "modules" / module_id
        src_dir = self.root / "src" / "modules" / module_id / item_name
        config_dir.mkdir(parents=True)
        data_dir.mkdir(parents=True)
        src_dir.mkdir(parents=True)

        (config_dir / "module.yaml").write_text(
            yaml.safe_dump(
                {
                    "schema_version": 1,
                    "id": module_id,
                    "version": "1.0.0",
                    "dependencies": [],
                }
            ),
            encoding="utf-8",
        )
        (config_dir / "deployment_config.yaml").write_text(
            yaml.safe_dump(
                {
                    "workspace": "FOS",
                    "connections": {"fabric_connection": "fabric"},
                    "connection_specs": {
                        "fabric_connection": {
                            "base_url": "https://api.fabric.microsoft.com",
                            "audience": "https://api.fabric.microsoft.com",
                        }
                    },
                    "semantic_model_lakehouses": {},
                    "folders": [{"name": module_id, "items": [item_name]}],
                }
            ),
            encoding="utf-8",
        )
        fos_id = str(uuid.uuid3(uuid.NAMESPACE_DNS, "FOS" + item_name))
        connection_id = str(uuid.uuid3(uuid.NAMESPACE_DNS, "FOSfabric"))
        (config_dir / "deployment_order.json").write_text(
            json.dumps(
                [
                    {"name": "fabric", "fos_id": connection_id},
                    {"name": item_name, "fos_id": fos_id},
                ]
            ),
            encoding="utf-8",
        )
        (data_dir / f"{module_id}.json").write_text("{}", encoding="utf-8")
        (src_dir / "item.txt").write_text(source_content, encoding="utf-8")

    def write_release(self, *module_ids):
        config = {
            "schema_version": 1,
            "release": {"name": "FOS", "version": "1.0.0"},
            "modules": [
                {"id": module_id, "enabled": True, "order": index}
                for index, module_id in enumerate(module_ids)
            ],
        }
        release_path = self.root / "config" / "release.yaml"
        release_path.parent.mkdir(parents=True, exist_ok=True)
        release_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    def test_non_deployable_module_requires_local_preview(self):
        self.add_module("preview", "Preview.Notebook")
        self.write_release("preview")
        release_path = self.root / "config" / "release.yaml"
        release = yaml.safe_load(release_path.read_text())
        release["modules"][0]["deployable"] = False
        release_path.write_text(yaml.safe_dump(release), encoding="utf-8")
        with self.assertRaisesRegex(CompositionError, "not ready for deployment"):
            compose_release(self.root, self.root / "blocked")
        summary = compose_release(self.root, self.root / "preview", preview=True)
        self.assertEqual(summary["modules"], ["preview"])

    def test_composes_two_modules_with_fos_prefixed_ids(self):
        self.add_module("first", "First.Notebook")
        self.add_module("second", "Second.Notebook")
        self.write_release("first", "second")

        output = self.root / "output"
        summary = compose_release(self.root, output)

        self.assertEqual(summary["modules"], ["first", "second"])
        order = json.loads((output / "config/deployment_order.json").read_text())
        self.assertEqual(len(order), 3)
        self.assertEqual(
            next(item["fos_id"] for item in order if item["name"] == "First.Notebook"),
            str(uuid.uuid3(uuid.NAMESPACE_DNS, "FOSFirst.Notebook")),
        )

    def test_rejects_conflicting_source_item_names(self):
        self.add_module("first", "Shared.Notebook", "first")
        self.add_module("second", "Shared.Notebook", "second")
        self.write_release("first", "second")

        with self.assertRaisesRegex(CompositionError, "both provide source item"):
            compose_release(self.root, self.root / "output")

    def test_selected_module_excludes_other_enabled_modules(self):
        self.add_module("first", "First.Notebook")
        self.add_module("second", "Second.Notebook")
        self.write_release("first", "second")

        output = self.root / "output"
        summary = compose_release(
            self.root,
            output,
            selected_modules=["second"],
        )

        self.assertEqual(summary["modules"], ["second"])
        self.assertTrue((output / "src/Second.Notebook").exists())
        self.assertFalse((output / "src/First.Notebook").exists())

    def test_preserves_same_named_folders_under_different_module_roots(self):
        self.add_module("first", "First.Notebook")
        self.add_module("second", "Second.Notebook")
        for module_id, item_name in (
            ("first", "First.Notebook"),
            ("second", "Second.Notebook"),
        ):
            config_path = (
                self.root / f"config/modules/{module_id}/deployment_config.yaml"
            )
            config = yaml.safe_load(config_path.read_text())
            config["folders"] = [
                {
                    "name": module_id.title(),
                    "folders": [
                        {"name": "Reporting", "items": [item_name]},
                    ],
                }
            ]
            config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
        self.write_release("first", "second")

        output = self.root / "output"
        compose_release(self.root, output)
        composed = yaml.safe_load(
            (output / "config/deployment_config.yaml").read_text()
        )

        self.assertEqual(
            [folder["name"] for folder in composed["folders"]],
            ["First", "Second"],
        )
        self.assertEqual(
            [folder["folders"][0]["name"] for folder in composed["folders"]],
            ["Reporting", "Reporting"],
        )

    def test_normalizes_direct_notebook_module_selection(self):
        self.assertIsNone(normalize_selected_modules(None))
        self.assertIsNone(normalize_selected_modules("all"))
        self.assertEqual(
            normalize_selected_modules("second, first,second"),
            ["second", "first"],
        )
        self.assertEqual(
            normalize_selected_modules(["first", "second"]),
            ["first", "second"],
        )
        with self.assertRaisesRegex(CompositionError, "cannot be combined"):
            normalize_selected_modules("all,first")

    def test_merges_distinct_module_deployment_metadata(self):
        self.add_module("first", "First.Notebook")
        self.add_module("second", "Second.Notebook")
        second_config_path = (
            self.root / "config/modules/second/deployment_config.yaml"
        )
        second_config = yaml.safe_load(second_config_path.read_text())
        second_config["connections"] = {"azure_connection": "azure"}
        second_config["connection_specs"] = {
            "azure_connection": {
                "base_url": "https://management.azure.com",
                "audience": "https://management.azure.com",
            }
        }
        second_config["semantic_model_lakehouses"] = {
            "Second.Notebook": "Second.Lakehouse"
        }
        second_config["post_deployment"] = {
            "jobs": [{"item": "Second.Notebook"}],
            "sql_endpoints": ["Second.Lakehouse"],
        }
        second_config_path.write_text(
            yaml.safe_dump(second_config), encoding="utf-8"
        )
        second_order_path = self.root / "config/modules/second/deployment_order.json"
        second_order = json.loads(second_order_path.read_text())
        second_order.extend(
            [
                {
                    "name": "azure",
                    "fos_id": str(uuid.uuid3(uuid.NAMESPACE_DNS, "FOSazure")),
                },
                {
                    "name": "Second.Lakehouse",
                    "fos_id": str(
                        uuid.uuid3(uuid.NAMESPACE_DNS, "FOSSecond.Lakehouse")
                    ),
                },
            ]
        )
        second_order_path.write_text(json.dumps(second_order), encoding="utf-8")
        self.write_release("first", "second")

        output = self.root / "output"
        compose_release(self.root, output)
        composed = yaml.safe_load(
            (output / "config/deployment_config.yaml").read_text()
        )

        self.assertEqual(set(composed["connections"]), {"fabric_connection", "azure_connection"})
        self.assertEqual(
            composed["semantic_model_lakehouses"]["Second.Notebook"],
            "Second.Lakehouse",
        )
        self.assertEqual(composed["post_deployment"]["jobs"], [{"item": "Second.Notebook"}])


if __name__ == "__main__":
    unittest.main()