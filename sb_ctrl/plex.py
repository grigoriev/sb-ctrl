"""Plex client: what the library already holds, and a scan of one path.

A file keeps its byte size when it moves from the seedbox into the library,
so the size is what tells whether a release is already there. That answer
holds however the file arrived, and it stops holding the moment somebody
deletes the file from Plex.
"""

from __future__ import annotations

import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable, Mapping

# movies are leaves themselves; a show keeps its files on the episodes
_LEAF_TYPE = {"movie": "1", "show": "4"}
# how long an index stays usable before the library is read again
INDEX_TTL = 30.0
TIMEOUT = 8.0

# fetch(path, params) -> the XML body Plex answered with
FetchFn = Callable[[str, dict[str, str]], str]


def match(
    files: Iterable[tuple[int, str]],
    sizes: Mapping[int, str],
    *,
    video_ext: Iterable[str],
    skip_patterns: Iterable[str],
) -> tuple[int, int]:
    """How many of a release's video files the library already holds.

    Only the files a delivery would keep are counted, so a sample or a text
    file beside the episodes never holds a pack back from counting as
    delivered.
    """
    exts = tuple(e if e.startswith(".") else f".{e}" for e in (str(x).lower() for x in video_ext))
    skips = [str(p).lower() for p in skip_patterns]
    wanted = [
        size for size, path in files if path.lower().endswith(exts) and not any(skip in path.lower() for skip in skips)
    ]
    return sum(1 for size in wanted if size in sizes), len(wanted)


class Plex:
    """Read-only view of a Plex library, plus a scan request."""

    def __init__(self, url: str, token: str, fetch: FetchFn | None = None) -> None:
        self._url = url.rstrip("/")
        self._token = token
        self._fetch: FetchFn = fetch or self._http_get

    @property
    def configured(self) -> bool:
        """Whether there is a server to ask at all."""
        return bool(self._url and self._token)

    def _http_get(self, path: str, params: dict[str, str]) -> str:  # pragma: no cover - network
        query = urllib.parse.urlencode({**params, "X-Plex-Token": self._token})
        with urllib.request.urlopen(f"{self._url}{path}?{query}", timeout=TIMEOUT) as response:  # noqa: S310
            body: bytes = response.read()
        return body.decode("utf-8", errors="replace")

    def _sections(self) -> list[tuple[str, str]]:
        """Every section as (key, leaf type), skipping the kinds with no files."""
        root = ET.fromstring(self._fetch("/library/sections", {}))  # noqa: S314 - the server is our own
        out = []
        for section in root.iter("Directory"):
            leaf = _LEAF_TYPE.get(section.get("type", ""))
            if leaf:
                out.append((section.get("key", ""), leaf))
        return out

    def part_sizes(self) -> dict[int, str]:
        """Byte size to file path for every file the library holds."""
        sizes: dict[int, str] = {}
        for key, leaf in self._sections():
            body = self._fetch(f"/library/sections/{key}/all", {"type": leaf})
            for part in ET.fromstring(body).iter("Part"):  # noqa: S314 - the server is our own
                size = int(part.get("size", 0))
                if size:
                    sizes[size] = part.get("file", "")
        return sizes

    def scan(self) -> None:
        """Ask Plex to look at the library, so a delivery shows up at once.

        Every section, with no path filter: sb-ctrl and Plex reach the same
        files through different mounts, so a path would need a mapping the
        scanner does not need. It skips what has not changed.
        """
        for key, _ in self._sections():
            self._fetch(f"/library/sections/{key}/refresh", {})

    def try_scan(self) -> bool:
        """Scan, and report whether it happened.

        A media server that is unset or unreachable is not a failure here:
        the delivery is already on disk, and Plex finds it on its own later.
        """
        if not self.configured:
            return False
        try:
            self.scan()
        except OSError, ET.ParseError:
            return False
        return True


class LibraryIndex:
    """The part sizes of the library, re-read at most every ``INDEX_TTL``.

    The torrent list is polled, and every poll would otherwise walk the whole
    library again.
    """

    def __init__(self, plex: Plex, ttl: float = INDEX_TTL, clock: Callable[[], float] = time.monotonic) -> None:
        self._plex = plex
        self._ttl = ttl
        self._clock = clock
        self._sizes: dict[int, str] | None = None
        self._read_at = 0.0

    def sizes(self) -> dict[int, str] | None:
        """The current index, or None when Plex cannot be reached or is unset."""
        if not self._plex.configured:
            return None
        now = self._clock()
        if self._sizes is not None and now - self._read_at < self._ttl:
            return self._sizes
        try:
            self._sizes = self._plex.part_sizes()
        except OSError, ET.ParseError, ValueError:
            return self._sizes
        self._read_at = now
        return self._sizes
