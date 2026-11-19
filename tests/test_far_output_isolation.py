"""Exercise the vendored runtime's physical bindings without Fabric credentials."""
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from uuid import UUID


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "src/modules/architecture-review/far-runtime"
sys.path.insert(0, str(RUNTIME))
try:
    from orchestration import runtime, storage
    from collectors import far_evidence
    from reports.agent import data_agent, sdk_deploy
    from reports.ontology import ontology
    from reports.owner import deployment, fabric_runtime, model
    from reports.powerbi import semantic_model
    from reports.powerbi.schema import GOLD_TABLES_BY_NAME
finally:
    sys.path.remove(str(RUNTIME))


class FarOutputIsolationTests(unittest.TestCase):
    def test_evidence_collapses_equivalent_observations_but_rejects_conflicts(self):
        workspace = str(UUID(int=1))
        now = datetime(2026, 11, 19, tzinfo=timezone.utc)
        snapshot = {
            "sha256": "test", "captured_at_utc": now.isoformat(),
            "configuration": {"sources": {"fuam": dict(enabled=True, layout="fos",
                workspace_id=workspace, lakehouse_id=workspace, max_age_hours=48)}, "thresholds": {}},
        }
        row = dict(WorkspaceId=workspace, WorkspaceName="test", CapacityId=None,
                   Description="", fuam_modified_at=now)
        older = {**row, "fuam_modified_at": now - timedelta(hours=1)}
        for pair in ([row, older], [older, row]):
            with patch.object(far_evidence, "_tenant_history", return_value=[]), \
                    patch.object(far_evidence, "fuam_facts", return_value={}):
                result = far_evidence.bind(snapshot, [{"id": workspace}],
                    lambda _, sql: pair if "FROM adm.workspaces " in sql else [], now=now)
            workspaces = result["tables"]["far_evidence_workspaces"]
            self.assertEqual(len(workspaces), 1)
            self.assertEqual(workspaces[0]["fuam_modified_at"], now.isoformat())
        with self.assertRaisesRegex(ValueError, "conflicting duplicate identities"):
            far_evidence.bind(snapshot, [{"id": workspace}],
                lambda *_: [row, {**older, "WorkspaceName": "conflict"}], now=now)

    def test_evidence_queries_use_selected_layout_and_preserve_output_contract(self):
        workspace, capacity, item = [str(UUID(int=n)) for n in (1, 2, 3)]
        resource = "/subscriptions/test/providers/microsoft.fabric/capacities/test"
        now = datetime(2026, 11, 19, tzinfo=timezone.utc)
        for layout in ("fos", "dbo"):
            with self.subTest(layout=layout):
                snapshot = {
                    "sha256": "test", "captured_at_utc": now.isoformat(),
                    "configuration": {
                        "sources": {name: dict(enabled=True, layout=layout, workspace_id=workspace,
                                               lakehouse_id=item, max_age_hours=48)
                                    for name in ("fuam", "fca")},
                        "thresholds": {},
                        "profiles": {"capacities": [{"id": capacity, "arm_resource_id": resource}]},
                    },
                }
                statements = []

                def query(source, sql):
                    statements.append((source, sql))
                    schema = ("adm" if source == "fuam" else "cost") if layout == "fos" else "dbo"
                    self.assertIn(f"FROM {schema}.", sql)
                    if "tenant_settings" in sql:
                        return []
                    if "resources" in sql:
                        return [dict(ResourceId=resource, ResourceName="capacity", RegionId="region", ResourceKey="key")]
                    table = next(name for name in far_evidence.CONTRACTS if f".{name} " in sql)
                    modified = "fos_modified_at" if layout == "fos" else "fuam_modified_at"
                    deleted = "fos_deleted" if layout == "fos" else "fuam_deleted"
                    self.assertIn(f"{modified} AS fuam_modified_at", sql)
                    self.assertIn(f"{deleted} = 0", sql)
                    id_column, columns, _ = far_evidence.CONTRACTS[table]
                    row = dict.fromkeys(columns, "")
                    row.update({id_column: capacity if table == "capacities" else workspace,
                                "fuam_modified_at": now})
                    if table == "active_items":
                        row["id"] = item
                    return [row]

                with patch.object(far_evidence, "fuam_facts", return_value={}), \
                        patch.object(far_evidence, "fca_capacity_tags", return_value={"table": "focus", "status": "available"}):
                    result = far_evidence.bind(snapshot, [{"id": workspace, "capacityId": capacity}], query, now=now)
                self.assertEqual(len(statements), 5)
                for _, (_, _, target) in far_evidence.CONTRACTS.items():
                    self.assertEqual(result["tables"][target][0]["fuam_modified_at"], now.isoformat())
                self.assertEqual(result["tables"]["far_evidence_capacity_resources"][0]["capacity_id"], capacity)

    def test_latest_search_is_confined_to_reviews(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            root = Path(folder)
            runs = root / "runs"
            for path in (runs / "old" / "raw", runs / "new" / "raw", runs / "no-evidence",
                         root / "runtime/source/raw", root / "orchestration/runs/fake/raw"):
                path.mkdir(parents=True)
            os.utime(runs / "old", (1, 1))
            with patch.object(storage, "REVIEW_RUNS", runs):
                self.assertEqual(storage.run_folder(storage.latest_run_id()), runs / "new")
                for bad in ("..", "../runtime/source", r"..\runtime", "/escape", "", "a:b"):
                    with self.subTest(bad=bad), self.assertRaises(ValueError):
                        storage.run_folder(bad)

    def test_both_models_and_ontology_bind_physical_schema_not_model_names(self):
        guid = str(UUID(int=1))
        for build in (model.build_bim, semantic_model.build_bim):
            bim = build("model", "server", guid)["model"]
            for table in bim["tables"]:
                self.assertNotIn(".", table["name"])
                for partition in table["partitions"]:
                    self.assertEqual(partition["source"]["schemaName"], "far")
                    self.assertNotIn(".", partition["source"]["entityName"])
        source = ontology.LakehouseSource(guid, "ws", guid, "FOS_Lakehouse", "server", guid)
        for entity in ontology.ENTITIES:
            tmdl = ontology.table_tmdl(entity, source, "2026-01-01T00:00:00Z")
            self.assertIn(f"entityName: {entity.table}\n\t\t\tschemaName: far\n", tmdl)

    def test_completed_target_excludes_only_its_reviewed_workspace_on_next_run(self):
        host, pipeline, parent, child, target, next_run = [str(UUID(int=n)) for n in range(1, 7)]
        config = {
            "CHILD_WORKSPACE_ID": host, "FUAM_WORKSPACE_ID": host,
            "CHILD_PIPELINE_ID": pipeline, "PARENT_RUN_ID": parent, "CHILD_RUN_ID": child,
            "RANKING_METRIC": "cu_seconds", "LOOKBACK_DAYS": "7", "TOP_N": "5",
            "NOTIFICATIONS_ENABLED": "false", "SKIP_REVIEWED_WITHIN_DAYS": "7",
            "COMPLETION_ACTION": "record_review",
        }
        def source(_):
            return "FUAM", [{"workspace_id": host, "metric_value": 20},
                            {"workspace_id": target, "metric_value": 10}]

        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            relative = storage.TARGETED_RUNS.relative_to(storage.FAR_FILES)
            self.assertEqual(relative.parts, ("orchestration", "runs"))
            state = Path(folder) / relative
            with patch.object(runtime, "TARGETED_RUNS", state):
                first = runtime.select_workspaces(config, parent, read_source=source, state_dir=state)
                self.assertEqual(first["workspace_ids"], target)
                self.assertEqual(runtime.run_completion(config)["workspace_ids"], [target])
                again = runtime.select_workspaces(config, next_run, read_source=source, state_dir=state)
                self.assertEqual(again["status"], "skipped_no_candidates")
                self.assertTrue((state / "completed" / f"{parent}.json").exists())

    def test_agent_deselects_homonyms_and_never_uses_default_schema_in_sql(self):
        name = "gold_workspaces"
        def schema(namespace):
            return {"name": namespace, "type": "x.schema", "children": [
                {"name": name, "type": "x.table", "is_selected": True,
                 "children": [{"name": c.name, "type": "x.column"}
                              for c in GOLD_TABLES_BY_NAME[name].columns]},
            ]}
        elements = [schema(namespace) for namespace in ("dbo", "far", "adm")]
        ds = MagicMock()
        ds.get_configuration.return_value = {"type": "lakehouse", "elements": elements}
        def select(namespace, table, value):
            self.assertEqual(table, name)
            next(e for e in elements if e["name"] == namespace)["children"][0]["is_selected"] = value
        ds.select.side_effect = lambda *path: select(*path, True)
        ds.unselect.side_effect = lambda *path: select(*path, False)
        # _select_tables lazily imports the approved column contract.
        with patch.object(sys, "path", [str(RUNTIME), *sys.path]):
            self.assertEqual(sdk_deploy._select_tables(ds, set()), {name})
        ds.select.assert_called_once_with("far", name)
        for example in data_agent.DEFAULT_LAKEHOUSE_FEWSHOTS:
            for table in re.findall(r"\bFROM\s+([\w.]+)", example["query"]):
                self.assertTrue(table.startswith("far.gold_"), table)

    def test_owner_merge_and_access_sync_bind_only_far(self):
        spark = MagicMock()
        with patch.object(sys, "path", [str(RUNTIME), *sys.path]):
            fabric_runtime._publish_owner_reviews(spark, MagicMock(), "sample-run")
        statements = "\n".join(call.args[0] for call in spark.sql.call_args_list)
        self.assertIn("MERGE INTO far.owner_workspaces", statements)
        self.assertIn("MERGE INTO far.owner_reviews", statements)
        self.assertNotRegex(statements, r"(?<!far\.)\bowner_(reviews|workspaces)\b")
        ids = [str(UUID(int=i)) for i in (1, 2, 3)]
        nb = deployment.access_notebook(RUNTIME, ids[0], ids[1], "FOS_Lakehouse", ids[2])
        code = "".join(nb["cells"][-1]["source"])
        compile(code, "<owner sync>", "exec")
        self.assertIn("saveAsTable('far.owner_access')", code)
        self.assertIn("spark.table('far.owner_workspaces')", code)
        self.assertEqual(nb["metadata"]["dependencies"]["lakehouse"]["default_lakehouse"], ids[1])
