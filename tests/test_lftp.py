from __future__ import annotations

from sb_ctrl.lftp import build_command


def test_mirror_for_a_folder() -> None:
    argv = build_command("host", "files/Show S01", True, "/staging/Show S01")
    assert argv[0] == "lftp"
    assert argv[-1] == "sftp://host"
    script = argv[2]
    assert "mirror -c 'files/Show S01' '/staging/Show S01'" in script
    assert script.endswith("bye")


def test_parallel_and_limit_rate() -> None:
    argv = build_command("host", "files/x", True, "/s/x", limit_rate="2M", parallel=4)
    script = argv[2]
    assert "set net:limit-rate 2M" in script
    assert "mirror -c --parallel=4" in script


def test_get_for_a_single_file() -> None:
    argv = build_command("host", "files/Movie.mkv", False, "/staging/Movie.mkv")
    assert "get -c files/Movie.mkv -o /staging/Movie.mkv" in argv[2]
