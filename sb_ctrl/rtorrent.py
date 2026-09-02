"""rTorrent XML-RPC client (read-only for now).

Lists completed downloads via ``d.multicall2`` and maps each item's absolute
``base_path`` on the seedbox to a path relative to the SFTP home, so lftp can
pull it. See SPEC.md section 5.
"""

from __future__ import annotations

import xmlrpc.client
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

RpcRow = list[Any]
# a call answers with rows, and system.multicall answers with a fault dict for
# any member call that failed, so the entries are not all rows
CallFn = Callable[..., list[Any]]

_FIELDS = [
    "d.hash=",
    "d.name=",
    "d.size_bytes=",
    "d.complete=",
    "d.base_path=",
    "d.is_multi_file=",
    "d.timestamp.finished=",
]


@dataclass(frozen=True)
class Torrent:
    hash: str
    name: str
    size: int
    is_multi: bool
    base_path: str
    base_rel: str
    finished: int


class RTorrent:
    """Minimal rTorrent XML-RPC client over HTTPS with Basic auth."""

    def __init__(
        self,
        url: str,
        user: str = "",
        password: str = "",
        sftp_base: str = "files",
        call: CallFn | None = None,
    ) -> None:
        self._url = url
        self._user = user
        self._password = password
        self._sftp_base = sftp_base
        self._call: CallFn = call or self._xmlrpc_call

    def _auth_url(self) -> str:
        if not self._user:
            return self._url
        parts = urlsplit(self._url)
        cred = f"{quote(self._user, safe='')}:{quote(self._password, safe='')}"
        netloc = f"{cred}@{parts.netloc}"
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))

    def _xmlrpc_call(self, method: str, *args: object) -> list[RpcRow]:  # pragma: no cover
        proxy = xmlrpc.client.ServerProxy(self._auth_url())
        result: Any = getattr(proxy, method)(*args)
        return list(result)

    def _to_rel(self, base_path: str) -> str:
        marker = f"/{self._sftp_base}/"
        idx = base_path.find(marker)
        if idx == -1:
            return base_path.lstrip("/")
        return base_path[idx + 1 :]

    def file_list(self, hashes: list[str]) -> dict[str, list[tuple[int, str]]]:
        """The size and path of every file of each torrent, in one request.

        The sizes are what match a release against the library, and asking
        per torrent would mean a round trip each. A torrent whose files
        cannot be read comes back with an empty list.
        """
        if not hashes:
            return {}
        calls = [{"methodName": "f.multicall", "params": [h, "", "f.size_bytes=", "f.path="]} for h in hashes]
        rows = self._call("system.multicall", calls)
        out: dict[str, list[tuple[int, str]]] = {}
        for h, result in zip(hashes, rows, strict=False):
            out[h] = [(int(entry[0]), str(entry[1])) for entry in result[0]] if isinstance(result, list) else []
        return out

    def list_completed(self) -> list[Torrent]:
        rows = self._call("d.multicall2", "", "main", *_FIELDS)
        torrents: list[Torrent] = []
        for row in rows:
            h, name, size, complete, base_path, is_multi, finished = row
            if int(complete) != 1:
                continue
            torrents.append(
                Torrent(
                    hash=str(h),
                    name=str(name),
                    size=int(size),
                    is_multi=bool(int(is_multi)),
                    base_path=str(base_path),
                    base_rel=self._to_rel(str(base_path)),
                    finished=int(finished),
                )
            )
        torrents.sort(key=lambda t: t.finished, reverse=True)
        return torrents
