# Security Policy

## Reporting a Vulnerability

Please report security issues privately through GitHub's
[private vulnerability reporting](https://github.com/grigoriev/sb-ctrl/security/advisories/new),
not through public issues. You will get a response within a few days.

## Authentication

The API has two ways in: a bearer token from `[api] token`, and a browser
session from `[auth]`. The server compares the token and the user name in
constant time.

When neither is configured, the API is open, so a fresh install can be set up.
`sb-ctrl serve` logs a warning at startup in that case. Configure a token or a
login before you expose the port.
