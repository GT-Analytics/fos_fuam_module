import base64
import ast
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

import yaml

MODULE = Path(__file__).resolve().parents[1] / "src/modules/architecture-review"
RUNTIME = MODULE / "far-runtime"
sys.path.insert(0, str(RUNTIME))
from orchestration.config_deployment import ensure_library, library_definition
from orchestration.deployment import notebook_parameter
from orchestration.fabric_api import FabricClient, FabricRequestError
from orchestration.folders import organize
from orchestration.setup import attached_fos_lakehouse, ensure_runtime_environment, load_stage
from orchestration.deployment import runtime_notebook
from reports.owner.deployment import access_notebook

INSTALLER = MODULE / "FOS_Install_FAR.Notebook/notebook-content.ipynb"
WS = "00000000-0000-0000-0000-000000000001"
LH = "00000000-0000-0000-0000-000000000002"
ENV = "00000000-0000-0000-0000-000000000003"


class NativeInstallTests(unittest.TestCase):
    def test_attachment_fails_before_writes_and_never_adopts_another_lakehouse(self):
        context = dict(currentWorkspaceId=WS, defaultLakehouseId=LH, defaultLakehouseWorkspaceId=LH)
        client = Mock()
        with self.assertRaises(ValueError):
            attached_fos_lakehouse(client, context)
        self.assertFalse(client.mock_calls)
        context["defaultLakehouseWorkspaceId"] = WS
        client.get_json.return_value = {"id": LH, "displayName": "Another lakehouse"}
        with self.assertRaisesRegex(ValueError, "FOS_Lakehouse"):
            attached_fos_lakehouse(client, context)
        client.get_json.return_value["displayName"] = "FOS_Lakehouse"
        self.assertEqual(attached_fos_lakehouse(client, context), (WS, LH))
        with self.assertRaises(ValueError):
            organize(client, WS, [(LH, "Lakehouse", "FAR")])
        client.request.assert_not_called()

    def test_stage_definitions_and_pipeline_expressions(self):
        nb = json.loads(INSTALLER.read_bytes())
        scope = {"wid": WS, "lhid": LH, "REPO_DIR": str(RUNTIME), "Path": Path, "notebook_parameter": notebook_parameter}
        code = ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]
        exec(code[0], scope)
        stages = {}

        def stage(suffix, filename, **params):
            stages[suffix] = load_stage(RUNTIME, filename, WS, LH, {"FAR_ENVIRONMENT_LIBRARY": "Custom_Env"}, params)
            return suffix

        scope.update(stage=stage, upsert=lambda *_: "pipeline", definition_part=lambda _, obj: obj, LAKEHOUSE_NAME="FOS_Lakehouse")
        exec(next(cell for cell in code if "collect_id = stage(" in cell), scope)
        activities = scope["pipe"]["properties"]["activities"]
        self.assertEqual([a["typeProperties"]["notebookId"] for a in activities], ["01_Collect", "02_Analyze", "03_Report", "04_Gold"])
        for i, a in enumerate(activities):
            if i:
                self.assertEqual(a["dependsOn"], [{"activity": activities[i-1]["name"], "dependencyConditions": ["Succeeded"]}])
            self.assertEqual(a["typeProperties"]["parameters"]["RUN_ID"]["value"],
                             {"value": "@pipeline().RunId", "type": "Expression"})
        for staged in stages.values():
            dep = staged["metadata"]["dependencies"]["lakehouse"]
            self.assertEqual((dep["default_lakehouse"], dep["default_lakehouse_workspace_id"]), (LH, WS))
        params = "".join(stages["01_Collect"]["cells"][2]["source"])
        self.assertIn('FAR_ENVIRONMENT_LIBRARY = "Custom_Env"', params)

    def test_library_upgrade_keeps_values_and_value_sets(self):
        client = Mock()
        client.list_items.return_value = [{"id": LH, "displayName": "FAR_Test"}]
        old = library_definition({"fuam": {"enabled": True}})
        old["parts"].append({"path": "valueSets/customer.json", "payload": "customer bytes"})
        client.complete.side_effect = [{"definition": old}, {}]
        ensure_library(client, WS, "FAR_Test", {"fuam": {"enabled": False, "layout": "fos"}})
        self.assertEqual(len(client.request.call_args_list), 2)
        update = client.request.call_args.kwargs["json_body"]["definition"]["parts"]
        self.assertEqual(update[1:], old["parts"][1:])
        variables = json.loads(base64.b64decode(update[0]["payload"]))["variables"]
        self.assertEqual({e["name"]: e["value"] for e in variables}, {"fuam__enabled": True, "fuam__layout": "fos"})
        self.assertEqual(client.complete.call_args.kwargs, {"fetch_result": False})

    def test_stage_binds_runtime_environment_without_changing_lakehouse(self):
        environment = "00000000-0000-0000-0000-000000000003"
        notebook = load_stage(RUNTIME, "01_collect.ipynb", WS, LH, {}, {},
                              environment_id=environment)
        dependencies = notebook["metadata"]["dependencies"]
        self.assertEqual(dependencies["environment"],
                         {"environmentId": environment, "workspaceId": WS})
        self.assertEqual(dependencies["lakehouse"]["default_lakehouse"], LH)
        with self.assertRaises(ValueError):
            load_stage(RUNTIME, "01_collect.ipynb", WS, LH, {}, {},
                       environment_id="invalid")

    def test_owner_and_targeted_helpers_keep_runtime_and_lakehouse_bindings(self):
        helpers = [
            access_notebook(RUNTIME, WS, LH, "FOS_Lakehouse", LH, environment_id=ENV),
            *[runtime_notebook("bundle.zip", WS, LH, stage=stage,
                              child_pipeline_id=LH, environment_id=ENV)
              for stage in ("selection", "notifications")],
        ]
        for notebook in helpers:
            dependencies = notebook["metadata"]["dependencies"]
            self.assertEqual(dependencies["environment"], {"environmentId": ENV, "workspaceId": WS})
            self.assertEqual(dependencies["lakehouse"]["default_lakehouse"], LH)
            for cell in notebook["cells"]:
                if cell["cell_type"] == "code":
                    compile("".join(cell["source"]), "generated helper", "exec")

    def test_installer_stage_assigns_folders_and_stamps_targeted_runtime(self):
        notebook = json.loads(INSTALLER.read_bytes())
        cell = next("".join(cell["source"]) for cell in notebook["cells"]
                    if cell["cell_type"] == "code" and "def stage(" in "".join(cell["source"]))
        functions = [node for node in ast.parse(cell).body if isinstance(node, ast.FunctionDef)]
        client = Mock()
        client.upsert_item.return_value = ENV
        scope = dict(client=client, wid=WS, lhid=LH, runtime_environment_id=ENV, bindings={},
                     artifacts=[], NOTEBOOK_PREFIX="FabricArchReview", REPO_DIR=str(RUNTIME),
                     Path=Path, load_stage=load_stage)
        from orchestration.fabric_api import definition_part
        scope["definition_part"] = definition_part
        exec(compile(ast.Module(body=functions, type_ignores=[]), "installer helpers", "exec"), scope)
        for suffix, filename, folder, parameters in [
            ("01_Collect", "01_collect.ipynb", "FAR/Notebooks", {}),
            ("05_Agent", "05_agent.ipynb", "FAR/Governance", {}),
            ("08_OwnerAgent", "08_owner_agent.ipynb", "FAR/Workspace Owner", {}),
            ("06_TargetedReviewSetup", "06_targeted_review_setup.ipynb", "FAR/Extensions",
             {"RUNTIME_ENVIRONMENT_ID": ENV}),
        ]:
            scope["stage"](suffix, filename, **parameters)
            self.assertEqual(scope["artifacts"][-1], (ENV, "Notebook", folder))
            definition = client.upsert_item.call_args.args[3]
            staged = json.loads(base64.b64decode(definition["parts"][0]["payload"]))
            self.assertEqual(staged["metadata"]["dependencies"]["environment"]["environmentId"], ENV)
            if parameters:
                self.assertIn(f'RUNTIME_ENVIRONMENT_ID = "{ENV}"',
                              "".join(staged["cells"][1]["source"]))

    def test_environment_first_install_and_redeploy_publish_only_when_needed(self):
        state = {"exists": False, "published": {}, "staged": {}, "phase": None}
        client = Mock(timeout_seconds=30)
        client.clock.return_value = 0
        client.list_items.side_effect = lambda *_: (
            [{"id": ENV, "displayName": "FAR_Runtime"}] if state["exists"] else [])
        client.get_json.side_effect = lambda _: {"properties": {"publishDetails": {"state": state["phase"]}}}
        client.complete.side_effect = lambda response, **_: response.json()

        def request(method, path, **kwargs):
            response = Mock(status_code=200, headers={})
            response.json.return_value = {}
            if method == "POST" and path.endswith("/environments"):
                state["exists"] = True
                response.json.return_value = {"id": ENV}
            elif method == "GET":
                document = state["staged" if "/staging/" in path else "published"]
                if not document:
                    response.status_code = 404
                    response.json.return_value = {"errorCode": (
                        "EnvironmentLibrariesNotFound" if "/staging/" in path
                        else "EnvironmentPublicLibrariesNotFound"
                    )}
                    raise FabricRequestError(method, path, response)
                response.text = yaml.safe_dump(document)
            elif path.endswith("/importExternalLibraries"):
                state["staged"] = yaml.safe_load(kwargs["data"])
            elif path.endswith("/publish?beta=false"):
                state["published"] = state["staged"]
                state["phase"] = "Success"
            else:
                self.fail(f"Unexpected environment request: {method} {path}")
            return response

        client.request.side_effect = request
        self.assertEqual(ensure_runtime_environment(client, WS, RUNTIME / "requirements.txt"), ENV)
        first_writes = [call for call in client.request.call_args_list if call.args[0] == "POST"]
        self.assertEqual(len(first_writes), 3)
        imported = first_writes[1].kwargs["data"]
        self.assertIn(b"mssql-python", imported)
        self.assertEqual(ensure_runtime_environment(client, WS, RUNTIME / "requirements.txt"), ENV)
        self.assertEqual([call for call in client.request.call_args_list if call.args[0] == "POST"], first_writes)

        state["staged"] = {"dependencies": [{"pip": ["customer-pending-edit"]}]}
        with self.assertRaisesRegex(ValueError, "unpublished"):
            ensure_runtime_environment(client, WS, RUNTIME / "requirements.txt")
        state["phase"] = "Running"
        with self.assertRaisesRegex(RuntimeError, "in progress"):
            ensure_runtime_environment(client, WS, RUNTIME / "requirements.txt")

    def test_environment_failure_and_timeout_stop_installation(self):
        client = Mock(timeout_seconds=30)
        client.list_items.return_value = [{"id": ENV, "displayName": "FAR_Runtime"}]
        client.get_json.side_effect = [
            {"properties": {}}, {"properties": {}},
            {"properties": {"publishDetails": {"state": "Failed"}}},
        ]
        response = Mock(text="dependencies: []")
        client.request.return_value = response
        client.clock.return_value = 0
        with self.assertRaisesRegex(RuntimeError, "did not succeed"):
            ensure_runtime_environment(client, WS, RUNTIME / "requirements.txt")
        client.get_json.side_effect = [{"properties": {}}, {"properties": {}}]
        client.clock.side_effect = [0, 31]
        with self.assertRaises(TimeoutError):
            ensure_runtime_environment(client, WS, RUNTIME / "requirements.txt")
        client.get_json.side_effect = None
        client.get_json.return_value = {"properties": {}}
        response.status_code = 403
        response.headers = {}
        response.json.return_value = {"errorCode": "InsufficientPrivileges"}
        client.request.side_effect = FabricRequestError("GET", "/libraries", response)
        with self.assertRaises(FabricRequestError):
            ensure_runtime_environment(client, WS, RUNTIME / "requirements.txt")

    def test_binary_environment_upload_has_correct_content_type_and_no_json(self):
        transport = Mock(return_value=Mock(status_code=200))
        client = FabricClient(lambda: "test-token", transport=transport)
        client.request("POST", f"/workspaces/{WS}/environments/{ENV}/staging/libraries/importExternalLibraries",
                       data=b"dependencies: []")
        self.assertEqual(transport.call_args.kwargs["headers"]["Content-Type"], "application/octet-stream")
        self.assertEqual(transport.call_args.kwargs["data"], b"dependencies: []")
        self.assertNotIn("json", transport.call_args.kwargs)

    def test_nested_folders_are_parent_scoped_and_redeployment_is_idempotent(self):
        root, target, unrelated = (f"00000000-0000-0000-0000-{i:012d}" for i in (4, 5, 6))
        folders = [{"id": root, "displayName": "FAR"},
                   {"id": unrelated, "displayName": "Notebooks", "parentFolderId": None}]
        item = {"id": ENV, "type": "Notebook"}
        client = Mock()
        client.get_json.side_effect = lambda path: {"value": folders} if "/folders?" in path else dict(item)

        def request(method, path, *, json_body):
            response = Mock()
            if path.endswith("/folders"):
                created = {"id": target, **json_body}
                folders.append(created)
                response.status_code = 201
                response.json.return_value = created
            else:
                self.assertEqual(path, f"/workspaces/{WS}/items/{ENV}/move")
                item["folderId"] = json_body["targetFolderId"]
                response.status_code = 200
                response.json.return_value = {"value": [dict(item)]}
            return response

        client.request.side_effect = request
        organize(client, WS, [(ENV, "Notebook", "FAR/Notebooks")])
        self.assertEqual(item["folderId"], target)
        self.assertEqual(folders[-1]["parentFolderId"], root)
        self.assertEqual(client.request.call_count, 2)
        organize(client, WS, [(ENV, "Notebook", "FAR/Notebooks")])
        self.assertEqual(client.request.call_count, 2)
        with self.assertRaises(ValueError):
            organize(client, WS, [(ENV, "Notebook", "Other/Notebooks")])
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            organize(client, WS, [(ENV, "Notebook", "FAR/Notebooks"), (ENV, "Notebook", "FAR/Extensions")])
        folders.append(dict(folders[-1], id=unrelated))
        with self.assertRaisesRegex(ValueError, "Multiple folders"):
            organize(client, WS, [(ENV, "Notebook", "FAR/Notebooks")])

    def test_notebooks_parse_without_magics_or_download_commands(self):
        for path in [INSTALLER, *(RUNTIME / "fabric/notebooks").glob("*.ipynb")]:
            with self.subTest(path=path):
                nb = json.loads(path.read_bytes())
                code = "\n".join("".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code")
                compile(code, str(path), "exec")
                self.assertNotRegex(code, r"(?i)\bgit\b.*\b(fetch|clone)\b|pip.*install|GITHUB_REPO_URL")
