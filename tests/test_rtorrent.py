from __future__ import annotations

from typing import Any

from sb_ctrl.rtorrent import RpcRow, RTorrent

# hash, name, size, complete, base_path, is_multi, finished
ROWS: list[RpcRow] = [
    ["H1", "Old Movie", 100, 1, "/home/u/files/Old Movie.mkv", 0, 1000],
    ["H2", "New Show", 200, 1, "/home/u/files/New Show", 1, 3000],
    ["H3", "Downloading", 50, 0, "/home/u/files/Downloading", 1, 2000],
]


def _client(rows: list[RpcRow]) -> RTorrent:
    def fake_call(method: str, *args: object) -> list[RpcRow]:
        assert method == "d.multicall2"
        return rows

    return RTorrent("https://x/xmlrpc", "u", "p", "files", call=fake_call)


def test_lists_only_completed_newest_first() -> None:
    torrents = _client(ROWS).list_completed()
    assert [t.name for t in torrents] == ["New Show", "Old Movie"]


def test_maps_fields_and_relative_path() -> None:
    torrents = _client(ROWS).list_completed()
    show = torrents[0]
    assert show.hash == "H2"
    assert show.size == 200
    assert show.is_multi is True
    assert show.base_rel == "files/New Show"
    movie = torrents[1]
    assert movie.is_multi is False
    assert movie.base_rel == "files/Old Movie.mkv"


def test_rel_path_without_marker_strips_leading_slash() -> None:
    rows: list[RpcRow] = [["H", "X", 1, 1, "/other/place/X", 0, 5]]
    assert _client(rows).list_completed()[0].base_rel == "other/place/X"


def test_auth_url_embeds_credentials() -> None:
    client = RTorrent("https://host/xmlrpc", "user@x", "p/w", "files")
    assert client._auth_url() == "https://user%40x:p%2Fw@host/xmlrpc"


def test_auth_url_without_user_is_unchanged() -> None:
    client = RTorrent("https://host/xmlrpc", "", "", "files")
    assert client._auth_url() == "https://host/xmlrpc"


def test_file_list_asks_for_every_torrent_in_one_call() -> None:
    seen: list[object] = []

    def fake_call(method: str, *args: object) -> list[RpcRow]:
        assert method == "system.multicall"
        seen.append(args[0])
        return [[[[100, "A/S01E01.mkv"], [200, "A/sample.mkv"]]], [[[300, "B.mkv"]]]]

    client = RTorrent("https://x/xmlrpc", "u", "p", "files", call=fake_call)
    assert client.file_list(["H1", "H2"]) == {
        "H1": [(100, "A/S01E01.mkv"), (200, "A/sample.mkv")],
        "H2": [(300, "B.mkv")],
    }
    assert len(seen) == 1


def test_file_list_of_nothing_asks_nothing() -> None:
    def fake_call(method: str, *args: object) -> list[RpcRow]:
        raise AssertionError("no call expected")

    assert RTorrent("https://x/xmlrpc", call=fake_call).file_list([]) == {}


def test_file_list_survives_a_torrent_rtorrent_cannot_read() -> None:
    def fake_call(method: str, *args: object) -> list[Any]:
        return [{"faultCode": -501, "faultString": "no such torrent"}, [[[300, "B.mkv"]]]]

    client = RTorrent("https://x/xmlrpc", call=fake_call)
    assert client.file_list(["H1", "H2"]) == {"H1": [], "H2": [(300, "B.mkv")]}
