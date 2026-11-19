# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Validate the FOS installer attachment, bind stage notebooks, and provision opt-in targeting."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from orchestration.deployment import DEFAULTS, deploy
from orchestration.fabric_api import FabricClient, FabricRequestError, guid
from orchestration.runtime import validate_config
from orchestration.sources import capacity_selector, validate_source


def ensure_runtime_environment(client: FabricClient, workspace_id: str, requirements: Path) -> str:
    """Publish the packaged dependencies before binding any FAR notebooks."""
    import yaml

    packages = [line.strip() for line in requirements.read_text(encoding="utf-8-sig").splitlines()
                if line.strip() and not line.lstrip().startswith("#")]
    if not packages or any(line.startswith("-") for line in packages):
        raise ValueError("FAR runtime requirements must contain package specifications.")
    desired = {"dependencies": [{"pip": packages}]}
    body = yaml.safe_dump({"name": "far-runtime", **desired}, sort_keys=False).encode("utf-8")
    workspace_id = guid(workspace_id)
    matches = [item for item in client.list_items(workspace_id, "Environment")
               if item["displayName"].casefold() == "far_runtime"]
    if len(matches) > 1:
        raise ValueError("Multiple FAR_Runtime Environments exist; resolve their identities before setup.")
    if matches:
        environment_id = guid(matches[0]["id"])
    else:
        item = client.complete(client.request(
            "POST", f"/workspaces/{workspace_id}/environments",
            json_body={"displayName": "FAR_Runtime",
                       "description": "FAR runtime requirements for the FOS architecture-review module."},
        ))
        environment_id = guid(item["id"])
    base = f"/workspaces/{workspace_id}/environments/{environment_id}"

    def state() -> str | None:
        properties = client.get_json(base).get("properties") or {}
        return (properties.get("publishDetails") or {}).get("state")

    def libraries(staging: bool) -> dict[str, Any]:
        path = base + ("/staging" if staging else "") + "/libraries/exportExternalLibraries"
        try:
            response = client.request("GET", path)
        except FabricRequestError as exc:
            if (exc.response.status_code != 404
                    or exc.response.json().get("errorCode") not in (
                        "EnvironmentLibrariesNotFound", "EnvironmentPublicLibrariesNotFound",
                    )):
                raise
            return {}
        document = yaml.safe_load(response.text)
        if not isinstance(document, dict) or not isinstance(document.get("dependencies"), list):
            raise ValueError("FAR_Runtime returned an invalid external-library definition.")
        return {key: value for key, value in document.items() if key != "name"}

    if state() in ("Running", "Waiting", "Cancelling", "NotStarted"):
        raise RuntimeError("FAR_Runtime publication is in progress. Wait for it to finish and rerun setup.")
    published, staged = libraries(False), libraries(True)
    if staged not in (published, desired):
        raise ValueError("FAR_Runtime has unpublished library edits. Review them before rerunning setup.")
    if state() == "Success" and published == desired and staged == desired:
        print("FAR_Runtime: packaged libraries already published.")
        return environment_id
    print("FAR_Runtime: publishing packaged libraries; this can take several minutes.")
    client.complete(client.request(
        "POST", base + "/staging/libraries/importExternalLibraries", data=body,
    ), fetch_result=False)
    client.complete(client.request("POST", base + "/staging/publish?beta=false"), fetch_result=False)
    deadline = client.clock() + client.timeout_seconds
    while client.clock() < deadline:
        current = state()
        if current == "Success":
            if libraries(False) != desired:
                raise RuntimeError("FAR_Runtime publication did not retain the packaged libraries.")
            return environment_id
        if current not in ("Running", "Waiting", "NotStarted"):
            raise RuntimeError(f"FAR_Runtime publication did not succeed (state {current!r}).")
        client.sleep(10)
    raise TimeoutError("FAR_Runtime publication timed out. Inspect the Environment before rerunning setup.")


def attached_fos_lakehouse(client: FabricClient, context: dict[str, Any]) -> tuple[str, str]:
    """Resolve the target by runtime attachment, never by creating or selecting a Lakehouse."""
    workspace_id = guid(context.get("currentWorkspaceId") or context.get("workspaceId") or "")
    lakehouse_id = guid(context.get("defaultLakehouseId") or "")
    validate_attachment(workspace_id, lakehouse_id, context)
    item = client.get_json(f"/workspaces/{workspace_id}/lakehouses/{lakehouse_id}")
    if item.get("displayName") != "FOS_Lakehouse" or item.get("id") != lakehouse_id:
        raise ValueError("The installer requires this workspace's existing FOS_Lakehouse as default.")
    return workspace_id, lakehouse_id


def load_stage(source: Path, filename: str, workspace_id: str, lakehouse_id: str,
               bindings: dict[str, str], parameters: dict[str, str], *,
               environment_id: str = "") -> dict[str, Any]:
    import json
    from orchestration.config_deployment import stamp_notebook_bindings
    from orchestration.deployment import stamp_parameters

    notebook = json.loads((source / "fabric" / "notebooks" / filename).read_text(encoding="utf-8-sig"))
    notebook = stamp_parameters(stamp_notebook_bindings(notebook, bindings), parameters)
    notebook.setdefault("metadata", {}).setdefault("dependencies", {})["lakehouse"] = {
        "default_lakehouse": guid(lakehouse_id),
        "default_lakehouse_name": "FOS_Lakehouse",
        "default_lakehouse_workspace_id": guid(workspace_id),
        "known_lakehouses": [{"id": guid(lakehouse_id)}],
    }
    if environment_id:
        notebook["metadata"]["dependencies"]["environment"] = {
            "environmentId": guid(environment_id), "workspaceId": guid(workspace_id),
        }
    return notebook


def validate_attachment(workspace_id: str, lakehouse_id: str, context: dict[str, Any]) -> None:
    if (
        str(context.get("defaultLakehouseId") or "").lower() != guid(lakehouse_id)
        or str(context.get("defaultLakehouseWorkspaceId") or "").lower() != guid(workspace_id)
    ):
        raise ValueError(
            "The setup notebook's default Lakehouse does not match WORKSPACE_ID/LAKEHOUSE_ID. "
            "Attach FOS_Lakehouse and restart the session before provisioning."
        )


def provision(
    client: FabricClient, *, workspace_id: str, lakehouse_id: str, child_pipeline_id: str,
    repo_dir: Path, name: str,
    defaults: dict[str, str], context: dict[str, Any] | None = None,
    owner_access_notebook_id: str = "",
    connections_library: str = "",
    environment_library: str = "FAR_Environment",
    environment_id: str = "",
) -> dict[str, str]:
    if context is None:
        import notebookutils
        context = dict(notebookutils.runtime.context)
    validate_attachment(workspace_id, lakehouse_id, context)
    if not isinstance(owner_access_notebook_id, str):
        raise ValueError("OWNER_ACCESS_NOTEBOOK_ID must be a string.")
    owner_access_notebook_id = owner_access_notebook_id.strip()
    if owner_access_notebook_id:
        owner_access_notebook_id = guid(owner_access_notebook_id)
    if not name.strip():
        raise ValueError("PARENT_PIPELINE_NAME is required.")
    options = {**DEFAULTS, **defaults, "NOTIFICATIONS_ENABLED": "false"}
    options["CAPACITY_ID_OR_NAME"] = capacity_selector(options["CAPACITY_ID_OR_NAME"])
    validation_options = dict(options)
    if connections_library:
        import notebookutils
        from orchestration.review_config import targeting_source
        validation_options.update(targeting_source(
            notebookutils.variableLibrary.getLibrary, connections_library, context=context,
        ))
    validate_config(validation_options)
    validate_source(validation_options)
    return deploy(
        client, workspace_id=guid(workspace_id), lakehouse_id=guid(lakehouse_id),
        child_pipeline_id=guid(child_pipeline_id), repo_dir=repo_dir, name=name,
        defaults=options,
        environment_library=environment_library,
        environment_id=environment_id,
        **({"connections_library": connections_library} if connections_library else {}),
        **({"owner_access_notebook_id": owner_access_notebook_id}
           if owner_access_notebook_id else {}),
    )
