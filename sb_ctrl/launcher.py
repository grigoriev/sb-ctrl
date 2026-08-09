"""Launch the transfer worker as a background process (SPEC.md section 8).

On a systemd host ``systemd-run --user`` keeps the transfer alive after the
SSH session ends (with lingering enabled). Inside a container there is no
systemd, so the worker is started as a detached child process instead. The
detached spawn returns at once, so the API request is never blocked for the
duration of the transfer.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable

Runner = Callable[[list[str]], int]
Spawner = Callable[[list[str]], None]


def systemd_argv(job_id: str) -> list[str]:
    return ["systemd-run", "--user", "--unit", f"sb-ctrl-{job_id}", "--", "sb-ctrl", "run-job", job_id]


def worker_argv(job_id: str) -> list[str]:
    return ["sb-ctrl", "run-job", job_id]


def _run(argv: list[str]) -> int:  # pragma: no cover - spawns a real process
    try:
        return subprocess.call(argv)
    except FileNotFoundError:
        return 127


def _spawn(argv: list[str]) -> None:  # pragma: no cover - spawns a real process
    subprocess.Popen(argv, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def launch(job_id: str, runner: Runner = _run, spawner: Spawner = _spawn) -> str:
    """Start the worker for ``job_id``.

    Use ``systemd-run`` when it succeeds; otherwise spawn a detached process.
    """
    if runner(systemd_argv(job_id)) == 0:
        return "systemd"
    spawner(worker_argv(job_id))
    return "spawn"
