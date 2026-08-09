from __future__ import annotations

from sb_ctrl import launcher


def test_argv_builders() -> None:
    assert launcher.systemd_argv("J1") == [
        "systemd-run",
        "--user",
        "--unit",
        "sb-ctrl-J1",
        "--",
        "sb-ctrl",
        "run-job",
        "J1",
    ]
    assert launcher.worker_argv("J1") == ["sb-ctrl", "run-job", "J1"]


def test_launch_uses_systemd_when_it_succeeds() -> None:
    calls: list[list[str]] = []
    spawned: list[list[str]] = []

    def runner(argv: list[str]) -> int:
        calls.append(argv)
        return 0

    assert launcher.launch("J1", runner, spawned.append) == "systemd"
    assert calls == [launcher.systemd_argv("J1")]
    assert spawned == []


def test_launch_spawns_detached_when_systemd_absent() -> None:
    calls: list[list[str]] = []
    spawned: list[list[str]] = []

    def runner(argv: list[str]) -> int:
        calls.append(argv)
        return 127

    assert launcher.launch("J1", runner, spawned.append) == "spawn"
    assert calls == [launcher.systemd_argv("J1")]
    assert spawned == [launcher.worker_argv("J1")]
