# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
"""Load only the installer-staged FAR source (also in warm Spark sessions)."""
import importlib
import os
import sys
from pathlib import Path

REPO_DIR = str(Path(__file__).resolve().parents[1])
if REPO_DIR in sys.path:
    sys.path.remove(REPO_DIR)
sys.path.insert(0, REPO_DIR)
for name in list(sys.modules):
    if name.partition(".")[0] in {"collectors", "analyzers", "orchestration", "reports"}:
        del sys.modules[name]
importlib.invalidate_caches()
sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
from orchestration.project import validate_checkout

validate_checkout(Path(REPO_DIR))
