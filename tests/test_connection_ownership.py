import json
import unittest
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4


class ConnectionOwnershipTest(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[1] / "scripts" / "Deploy_FOS.ipynb"
        cells = json.loads(path.read_text(encoding="utf-8"))["cells"]
        self.cell = next("".join(c["source"]) for c in cells
                         if "def create_or_get_connection(" in "".join(c["source"]))
        self.http = Mock()
        self.group, self.conn = str(uuid4()), str(uuid4())
        utils = Mock()
        utils.credentials.getToken.return_value = "test-token"
        self.env = dict(requests=self.http, notebookutils=utils,
                        run_fab_command=Mock(side_effect=[None, self.conn]),
                        print_color=Mock(), connection_owner_group=self.group,
                        source_connections={"api": "Test API"}, mapping_table=[],
                        connection_specs={"api": {"base_url": "test", "audience": "test"}},
                        get_id_by_name=Mock())
        self.principal = {"id": self.group, "type": "Group"}

    def test_create_missing_group_owner(self):
        self.http.get.return_value.json.return_value = {"value": []}
        exec(self.cell, self.env)
        self.assertEqual(self.http.post.call_args.kwargs["json"],
                         {"principal": self.principal, "role": "Owner"})
        self.http.patch.assert_not_called()

    def test_reuse_with_existing_owner_or_lower_role(self):
        for role in ("Owner", "User"):
            with self.subTest(role=role):
                self.env["run_fab_command"].side_effect = [RuntimeError("already exists"), self.conn]
                assignment = {"id": str(uuid4()), "principal": self.principal, "role": role}
                self.http.get.side_effect = [
                    Mock(**{"json.return_value": {"value": [], "continuationToken": "next"}}),
                    Mock(**{"json.return_value": {"value": [assignment]}}),
                ]
                exec(self.cell, self.env)
                self.assertEqual(self.http.get.call_args.kwargs["params"], {"continuationToken": "next"})
                self.http.post.assert_not_called()
                if role == "Owner":
                    self.http.patch.assert_not_called()
                else:
                    self.assertTrue(self.http.patch.call_args.args[0].endswith("/" + assignment["id"]))
                    self.assertEqual(self.http.patch.call_args.kwargs["json"], {"role": "Owner"})

    def test_access_denied_fails_deployment(self):
        self.http.get.return_value.raise_for_status.side_effect = RuntimeError("Forbidden")
        with self.assertRaisesRegex(RuntimeError, "Forbidden"):
            exec(self.cell, self.env)
        self.http.post.assert_not_called()
