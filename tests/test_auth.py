"""Password hashing and session cookies."""

from __future__ import annotations

from sb_ctrl import auth

SECRET = "s3cr3t-signing-key"


def test_hash_verifies_its_own_password() -> None:
    stored = auth.hash_password("correct horse")
    assert auth.verify_password("correct horse", stored)
    assert not auth.verify_password("wrong horse", stored)


def test_hash_differs_per_salt() -> None:
    assert auth.hash_password("same") != auth.hash_password("same")


def test_malformed_hashes_never_match() -> None:
    assert not auth.verify_password("x", "")
    assert not auth.verify_password("x", "bcrypt$aaaa$bbbb")
    assert not auth.verify_password("x", "scrypt$a$bbbb")  # not decodable base64


def test_session_round_trip() -> None:
    cookie = auth.issue_session(SECRET, "sergey", ttl_seconds=60)
    assert auth.session_user(SECRET, cookie) == "sergey"


def test_session_rejects_another_secret() -> None:
    cookie = auth.issue_session(SECRET, "sergey", ttl_seconds=60)
    assert auth.session_user("other secret", cookie) is None


def test_session_rejects_tampering() -> None:
    cookie = auth.issue_session(SECRET, "sergey", ttl_seconds=60)
    payload, expires, signature = cookie.split(".")
    forged = f"{payload}.{int(expires) + 10_000}.{signature}"
    assert auth.session_user(SECRET, forged) is None


def test_session_expires() -> None:
    cookie = auth.issue_session(SECRET, "sergey", ttl_seconds=60, now=1000)
    assert auth.session_user(SECRET, cookie, now=1_030) == "sergey"
    assert auth.session_user(SECRET, cookie, now=1_100) is None


def test_session_rejects_junk() -> None:
    assert auth.session_user(SECRET, "not-a-cookie") is None
    assert auth.session_user(SECRET, "a.b.c") is None


def test_session_rejects_an_unreadable_payload() -> None:
    # Correctly signed, but the parts are not a user name and an expiry.
    payload = "!!!.notanumber"
    cookie = f"{payload}.{auth._sign(SECRET, payload)}"
    assert auth.session_user(SECRET, cookie) is None
