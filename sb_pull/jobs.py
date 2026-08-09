"""Transfer job state, stored under ``<staging_root>/.jobs/<id>/state.json``.

For now this reads job state for the ``status`` command; the worker that writes
it arrives with the transfer phase (SPEC.md section 8).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def jobs_dir(staging_root: str) -> Path:
    return Path(staging_root) / ".jobs"


def list_jobs(staging_root: str) -> list[dict[str, Any]]:
    """Return every job's state, newest id last. Empty when nothing is staged."""
    if not staging_root:
        return []
    root = jobs_dir(staging_root)
    if not root.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for entry in sorted(root.iterdir()):
        state = entry / "state.json"
        if not state.is_file():
            continue
        try:
            out.append(json.loads(state.read_text()))
        except (OSError, json.JSONDecodeError):
            continue
    return out
