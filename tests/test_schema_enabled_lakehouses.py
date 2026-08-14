import json
import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
MODULES_ROOT = REPO_ROOT / "src" / "modules"
LAKEHOUSE_TABLE_PATTERN = re.compile(
    r"\bFOS_(?:Lakehouse|Staging_Lakehouse|Config_Lakehouse|Backup_Lakehouse)\."
    r"(?!dbo(?:\.|\b)|Lakehouse\b)"
)
RELATIVE_TABLE_PATH_PATTERN = re.compile(r"(?<!/)Tables/(?!dbo/)")


class SchemaEnabledLakehouseTests(unittest.TestCase):
    def test_deployment_creates_schema_enabled_lakehouses(self):
        notebook = json.loads(
            (REPO_ROOT / "scripts" / "Deploy_FOS.ipynb").read_text(encoding="utf-8")
        )
        source = "\n".join(
            line
            for cell in notebook["cells"]
            for line in cell.get("source", [])
        )
        self.assertIn("enableSchemas=True", source)
        self.assertNotIn("enableSchemas=False", source)
        self.assertIn("properties.defaultSchema", source)
        self.assertEqual(source.count("properties.defaultSchema"), 1)
        self.assertIn("Existing non-schema", source)

    def test_each_module_notebook_selects_dbo_once(self):
        for path in MODULES_ROOT.rglob("*.ipynb"):
            with self.subTest(path=path):
                notebook = json.loads(path.read_text(encoding="utf-8"))
                count = sum(
                    line.strip() == 'spark.sql("USE dbo")'
                    for cell in notebook["cells"]
                    for line in cell.get("source", [])
                )
                self.assertEqual(count, 1)

    def test_notebook_table_references_are_dbo_qualified(self):
        violations = []
        for path in MODULES_ROOT.rglob("*.ipynb"):
            notebook = json.loads(path.read_text(encoding="utf-8"))
            for cell in notebook["cells"]:
                if cell.get("cell_type") != "code":
                    continue
                for line in cell.get("source", []):
                    if LAKEHOUSE_TABLE_PATTERN.search(line):
                        violations.append(f"{path}: {line.strip()}")
                    if (
                        RELATIVE_TABLE_PATH_PATTERN.search(line)
                        and '"Tables/' in line
                    ):
                        violations.append(f"{path}: {line.strip()}")
        self.assertEqual(violations, [])

    def test_pipeline_lookup_uses_dbo(self):
        pipeline_path = (
            MODULES_ROOT
            / "cost-analysis"
            / "Load Quota.DataPipeline"
            / "pipeline-content.json"
        )
        pipeline = json.loads(pipeline_path.read_text(encoding="utf-8"))
        serialized = json.dumps(pipeline)
        self.assertIn('"table": "dbo.subscriptions"', serialized)

    def test_direct_lake_partitions_use_dbo(self):
        table_files = list(MODULES_ROOT.rglob("*.SemanticModel/definition/tables/*.tmdl"))
        direct_lake_files = [
            path
            for path in table_files
            if "mode: directLake" in path.read_text(encoding="utf-8")
        ]
        self.assertTrue(direct_lake_files)
        for path in direct_lake_files:
            with self.subTest(path=path):
                self.assertIn("schemaName: dbo", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
