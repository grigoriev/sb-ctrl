from __future__ import annotations

from sb_ctrl.lftp import build_command, target_url


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


def test_url_gives_lftp_an_empty_password() -> None:
    # sftp://user@host makes lftp ask for a password and lose the user when it
    # cannot; the empty password sends it to the ssh key instead.
    assert target_url("sb.example.com", "ynzfh") == "sftp://ynzfh:@sb.example.com"


def test_url_without_a_user() -> None:
    assert target_url("sb.example.com") == "sftp://sb.example.com"


def test_url_leaves_a_host_that_already_carries_credentials() -> None:
    assert target_url("ynzfh:@sb.example.com", "someone") == "sftp://ynzfh:@sb.example.com"


def test_build_command_uses_the_user() -> None:
    argv = build_command("host", "files/x", False, "/s/x", user="u")
    assert argv[-1] == "sftp://u:@host"
