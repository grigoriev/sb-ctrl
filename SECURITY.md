# Security policy

## Reporting a vulnerability

Report a vulnerability privately through GitHub:
https://github.com/grigoriev/sb-ctrl/security/advisories/new
(the **Security** tab, **Report a vulnerability**). Do not open a public issue for it.

We answer within a week. The fix goes into the next release, and its release notes name it.

## Supported versions

Only the latest release gets fixes, and with it the image `ghcr.io/grigoriev/sb-ctrl:latest`.

## Scope

The code in `sb_ctrl/`, the Dockerfile, the scripts and the workflows belong to this repository.

Vulnerabilities in upstream software (Python, FastAPI and the other Python packages, lftp,
OpenSSH and the base image) belong to the upstream project. Tell us as well if this project is
affected, so we can release a fix when the upstream fix is out.

## Authentication

The API has two ways in: a bearer token from `[api] token`, and a browser
session from `[auth]`. The server compares the token and the user name in
constant time.

When neither is configured, the server fails closed: it refuses to start, and
it rejects every request with 401. Only `[api] allow_open = true` opens the API
without authentication. The server then logs a warning at startup. Use it only
on a host that nothing else can reach.
