"""Launch the transfer worker as a background unit (SPEC.md section 8).

``systemd-run --user`` keeps the transfer alive after the SSH session ends
(with lingering enabled). A ``nohup`` fallback is used when systemd is absent.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable

Runner = Callable[[list[str]], int]


def systemd_argv(job_id: str) -> list[str]:
    return ["systemd-run", "--user", "--unit", f"sb-pull-{job_id}", "--", "sb-pull", "run-job", job_id]


def nohup_argv(job_id: str) -> list[str]:
    return ["nohup", "sb-pull", "run-job", job_id]


def _run(argv: list[str]) -> int:  # pragma: no cover - spawns a real process
    return subprocess.call(argv)


def launch(job_id: str, runner: Runner = _run) -> str:
    """Start the worker for ``job_id``; fall back to nohup if systemd-run fails."""
    if runner(systemd_argv(job_id)) == 0:
        return "systemd"
    runner(nohup_argv(job_id))
    return "nohup"
