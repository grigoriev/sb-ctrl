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
    assert launcher.nohup_argv("J1") == ["nohup", "sb-ctrl", "run-job", "J1"]


def test_launch_uses_systemd_when_it_succeeds() -> None:
    calls: list[list[str]] = []

    def runner(argv: list[str]) -> int:
        calls.append(argv)
        return 0

    assert launcher.launch("J1", runner) == "systemd"
    assert calls == [launcher.systemd_argv("J1")]


def test_launch_falls_back_to_nohup() -> None:
    calls: list[list[str]] = []

    def runner(argv: list[str]) -> int:
        calls.append(argv)
        return 0 if argv[0] == "nohup" else 1

    assert launcher.launch("J1", runner) == "nohup"
    assert calls == [launcher.systemd_argv("J1"), launcher.nohup_argv("J1")]
