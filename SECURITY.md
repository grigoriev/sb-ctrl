# Security Policy

## Reporting a Vulnerability

Please report security issues privately through GitHub's
[private vulnerability reporting](https://github.com/grigoriev/sb-ctrl/security/advisories/new),
not through public issues. You will get a response within a few days.

## Authentication

The API has two ways in: a bearer token from `[api] token`, and a browser
session from `[auth]`. The server compares the token and the user name in
constant time.

When neither is configured, the server fails closed: it refuses to start, and
it rejects every request with 401. Only `[api] allow_open = true` opens the API
without authentication. The server then logs a warning at startup. Use it only
on a host that nothing else can reach.
