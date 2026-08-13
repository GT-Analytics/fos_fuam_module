import json
import tempfile
import unittest
import uuid
from pathlib import Path

import yaml

from cicd.release.compose_release import CompositionError, compose_release


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
                    "fos_lakehouse_semantic_models": [],
                    "folders": [{"name": module_id, "items": [item_name]}],
                }
            ),
            encoding="utf-8",
        )
        fos_id = str(uuid.uuid3(uuid.NAMESPACE_DNS, "FOS" + item_name))
        (config_dir / "deployment_order.json").write_text(
            json.dumps([{"name": item_name, "fos_id": fos_id}]),
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
        self.assertEqual(len(order), 2)
        self.assertEqual(
            order[0]["fos_id"],
            str(uuid.uuid3(uuid.NAMESPACE_DNS, "FOSFirst.Notebook")),
        )

    def test_rejects_conflicting_source_item_names(self):
        self.add_module("first", "Shared.Notebook", "first")
        self.add_module("second", "Shared.Notebook", "second")
        self.write_release("first", "second")

        with self.assertRaisesRegex(CompositionError, "both provide source item"):
            compose_release(self.root, self.root / "output")


if __name__ == "__main__":
    unittest.main()