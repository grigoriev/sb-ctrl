from __future__ import annotations

from typing import Any

from sb_ctrl.plex import LibraryIndex, Plex, match

SECTIONS = """<MediaContainer>
  <Directory key="1" type="movie" title="Films"/>
  <Directory key="2" type="show" title="Shows"/>
  <Directory key="3" type="photo" title="Pictures"/>
</MediaContainer>"""

MOVIES = """<MediaContainer>
  <Video><Media><Part file="/media/movies/A (2020)/A (2020).mkv" size="100"/></Media></Video>
</MediaContainer>"""

EPISODES = """<MediaContainer>
  <Video><Media><Part file="/media/series/B/Season 01/S01E01.mkv" size="200"/></Media></Video>
  <Video><Media><Part file="/media/series/B/Season 01/S01E02.mkv" size="300"/></Media></Video>
</MediaContainer>"""

EXT = [".mkv", ".mp4"]
SKIP = ["sample"]


class _FakePlex:
    """Answers the section and item requests, and counts them."""

    def __init__(self, bodies: dict[str, str] | None = None) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []
        self._bodies = bodies or {
            "/library/sections": SECTIONS,
            "/library/sections/1/all": MOVIES,
            "/library/sections/2/all": EPISODES,
        }

    def __call__(self, path: str, params: dict[str, str]) -> str:
        self.calls.append((path, params))
        return self._bodies.get(path, "<MediaContainer/>")


def _plex(fetch: Any) -> Plex:
    return Plex("http://plex:32400", "token", fetch=fetch)


def test_match_counts_only_the_files_a_delivery_keeps() -> None:
    files = [(200, "B/S01E01.mkv"), (300, "B/S01E02.mkv"), (7, "B/sample.mkv"), (9, "B/readme.nfo")]
    assert match(files, {200: "x", 300: "y"}, video_ext=EXT, skip_patterns=SKIP) == (2, 2)


def test_match_reports_a_partly_delivered_pack() -> None:
    files = [(200, "B/S01E01.mkv"), (300, "B/S01E02.mkv")]
    assert match(files, {200: "x"}, video_ext=EXT, skip_patterns=SKIP) == (1, 2)


def test_match_of_a_release_without_video_is_empty() -> None:
    assert match([(9, "B/readme.nfo")], {9: "x"}, video_ext=EXT, skip_patterns=SKIP) == (0, 0)


def test_part_sizes_reads_every_section_that_holds_files() -> None:
    fetch = _FakePlex()
    sizes = _plex(fetch).part_sizes()
    assert sizes == {
        100: "/media/movies/A (2020)/A (2020).mkv",
        200: "/media/series/B/Season 01/S01E01.mkv",
        300: "/media/series/B/Season 01/S01E02.mkv",
    }
    # a photo section holds no video, so it is never asked
    assert [path for path, _ in fetch.calls] == [
        "/library/sections",
        "/library/sections/1/all",
        "/library/sections/2/all",
    ]


def test_scan_refreshes_every_section() -> None:
    fetch = _FakePlex()
    _plex(fetch).scan()
    assert [path for path, _ in fetch.calls[1:]] == ["/library/sections/1/refresh", "/library/sections/2/refresh"]


def test_try_scan_says_nothing_happened_without_a_server() -> None:
    assert Plex("", "").try_scan() is False


def test_try_scan_survives_an_unreachable_server() -> None:
    def broken(path: str, params: dict[str, str]) -> str:
        raise OSError("no route")

    assert _plex(broken).try_scan() is False


def test_try_scan_reports_a_scan() -> None:
    assert _plex(_FakePlex()).try_scan() is True


def test_index_is_empty_without_a_server() -> None:
    assert LibraryIndex(Plex("", "")).sizes() is None


def test_index_reads_once_inside_its_ttl() -> None:
    fetch = _FakePlex()
    now = [1000.0]
    index = LibraryIndex(_plex(fetch), ttl=30, clock=lambda: now[0])
    assert index.sizes() == index.sizes()
    reads = len(fetch.calls)
    now[0] += 31
    index.sizes()
    assert len(fetch.calls) > reads


def test_index_keeps_the_last_answer_when_plex_goes_away() -> None:
    state = {"broken": False}

    def flaky(path: str, params: dict[str, str]) -> str:
        if state["broken"]:
            raise OSError("gone")
        return _FakePlex()(path, params)

    now = [1000.0]
    index = LibraryIndex(_plex(flaky), ttl=30, clock=lambda: now[0])
    first = index.sizes()
    state["broken"] = True
    now[0] += 31
    assert index.sizes() == first
