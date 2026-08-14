import json
import tempfile
import unittest
import uuid
from pathlib import Path

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