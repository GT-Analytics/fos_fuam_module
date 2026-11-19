# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""FAR-owned storage in the attached schema-enabled FOS Lakehouse.

Installer code lives in Files/far/runtime, never under a writable run root.
These paths route IO; they do not grant rights. Do not grant the results
writer write access to Files/far, runtime, or producer schemas.
"""
from pathlib import Path
import re


FAR_SCHEMA = "far"
FAR_FILES = Path("/lakehouse/default/Files/far")
REVIEW_RUNS = FAR_FILES / "runs"
TARGETED_RUNS = FAR_FILES / "orchestration" / "runs"
_RUN_ID = re.compile(r"[A-Za-z0-9_-]+")


def far_table(name: str) -> str:
    """Qualify logical table names without accepting a catalog, path or SQL."""
    if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        raise ValueError(f"Invalid FAR table name: {name!r}")
    return f"{FAR_SCHEMA}.{name}"


def run_folder(run_id: str) -> Path:
    if not isinstance(run_id, str) or not _RUN_ID.fullmatch(run_id):
        raise ValueError("Invalid FAR run ID; expected one path component.")
    return REVIEW_RUNS / run_id


def latest_run_id() -> str:
    candidates = (
        folder for folder in REVIEW_RUNS.iterdir()
        if _RUN_ID.fullmatch(folder.name) and (folder / "raw").is_dir()
    ) if REVIEW_RUNS.is_dir() else ()
    latest = max(candidates, key=lambda p: (p.stat().st_mtime_ns, p.name), default=None)
    if latest is None:
        raise ValueError("No FAR run with raw evidence found under Files/far/runs; run Collect first.")
    return latest.name
