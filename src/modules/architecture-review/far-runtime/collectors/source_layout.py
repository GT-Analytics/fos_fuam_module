# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Physical names for the fixed, read-only FAR source queries (never user SQL identifiers)."""
from dataclasses import dataclass


TABLE_SCHEMAS = {
    "fuam": {
        "activities": "adm", "active_items": "adm", "capacities": "adm", "workspaces": "adm",
        "tenant_settings": "adm", "tenant_settings_enabled_security_groups": "adm",
        "workspaces_scanned_users": "adm", "widelyshared_publishtoweb": "adm",
        "widelyshared_organization_links": "adm", "capacity_refreshable_details": "adm",
        "capacity_metrics_by_item_kind_by_day": "capacity_metrics",
        "capacity_metrics_by_item_by_operation_by_day": "capacity_metrics",
    },
    "fca": {"focus": "cost", "resources": "cost"},
}


@dataclass(frozen=True)
class SourceLayout:
    module: str
    layout: str = "dbo"  # Existing upstream snapshots have no layout field.

    def __post_init__(self):
        if self.module not in TABLE_SCHEMAS or self.layout not in ("dbo", "fos"):
            raise ValueError("Unsupported FAR source or layout (expected fos or dbo).")

    def table(self, name: str) -> str:
        schema = TABLE_SCHEMAS[self.module][name]
        return f"{schema if self.layout == 'fos' else 'dbo'}.{name}"

    @property
    def modified(self) -> str:
        return "fos_modified_at" if self.layout == "fos" else "fuam_modified_at"

    @property
    def deleted(self) -> str:
        return "fos_deleted" if self.layout == "fos" else "fuam_deleted"
