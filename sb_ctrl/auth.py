"""Single-user login: a scrypt password hash and a signed session cookie.

The server keeps no session store. The cookie carries the user name and an
expiry, signed with the configured secret, so a restart does not log anyone out
and any instance can check it. Everything here is standard library.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time

COOKIE_NAME = "sb_session"

_SCHEME = "scrypt"
_N = 2**14
_R = 8
_P = 1
_DKLEN = 32


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _derive(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)


def hash_password(password: str, salt: bytes | None = None) -> str:
    """Return a ``scrypt$salt$hash`` string to paste into the config file."""
    salt = secrets.token_bytes(16) if salt is None else salt
    return f"{_SCHEME}${_b64(salt)}${_b64(_derive(password, salt))}"


def verify_password(password: str, stored: str) -> bool:
    """Check a password against a stored hash. A malformed hash never matches."""
    parts = stored.split("$")
    if len(parts) != 3 or parts[0] != _SCHEME:
        return False
    try:
        # binascii.Error, raised on bad base64, is a ValueError.
        salt, expected = _unb64(parts[1]), _unb64(parts[2])
    except ValueError:
        return False
    return hmac.compare_digest(_derive(password, salt), expected)


def _sign(secret: str, payload: str) -> str:
    return _b64(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())


def issue_session(secret: str, user: str, ttl_seconds: int, now: float | None = None) -> str:
    """Mint a cookie value proving ``user`` until ``ttl_seconds`` from now."""
    expires = int((time.time() if now is None else now) + ttl_seconds)
    payload = f"{_b64(user.encode())}.{expires}"
    return f"{payload}.{_sign(secret, payload)}"


def session_user(secret: str, cookie: str, now: float | None = None) -> str | None:
    """Return the user a cookie proves, or None if it is forged or expired."""
    parts = cookie.split(".")
    if len(parts) != 3:
        return None
    payload = f"{parts[0]}.{parts[1]}"
    if not hmac.compare_digest(_sign(secret, payload), parts[2]):
        return None
    try:
        expires = int(parts[1])
        user = _unb64(parts[0]).decode()
    except ValueError, UnicodeDecodeError:
        return None
    if expires <= (time.time() if now is None else now):
        return None
    return user
