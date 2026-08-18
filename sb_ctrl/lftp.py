"""Build the lftp command that pulls a title from the seedbox (SPEC.md section 8)."""

from __future__ import annotations

import shlex


def target_url(host: str, user: str = "") -> str:
    """The sftp URL for lftp.

    The empty password matters. Given ``sftp://user@host`` lftp asks for a
    password, and with no terminal to ask it falls back to an anonymous login,
    dropping the user on the way; ``sftp://user:@host`` tells it to use the ssh
    key instead. A host that already carries credentials is left alone.
    """
    if not user or "@" in host:
        return f"sftp://{host}"
    return f"sftp://{user}:@{host}"


def build_command(
    host: str,
    base_rel: str,
    is_multi: bool,
    local_path: str,
    limit_rate: str = "",
    parallel: int = 1,
    user: str = "",
) -> list[str]:
    """The lftp argv to mirror (folder) or get (file) ``base_rel`` into ``local_path``."""
    steps: list[str] = []
    if limit_rate:
        steps.append(f"set net:limit-rate {limit_rate}")
    if is_multi:
        par = f" --parallel={parallel}" if parallel > 1 else ""
        steps.append(f"mirror -c{par} {shlex.quote(base_rel)} {shlex.quote(local_path)}")
    else:
        steps.append(f"get -c {shlex.quote(base_rel)} -o {shlex.quote(local_path)}")
    steps.append("bye")
    return ["lftp", "-e", "; ".join(steps), target_url(host, user)]
