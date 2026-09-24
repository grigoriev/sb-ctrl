# Changelog

All notable changes to this project are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
The project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Releases before 0.8.0 are listed on the
[GitHub releases page](https://github.com/grigoriev/sb-ctrl/releases).

## [Unreleased]

### Changed

- Release with the Bump Version & Release workflow. Its `v*` tag builds and pushes
  the image, then creates the GitHub release.
- The version bump moves the Unreleased entries of this changelog into a section for
  the new version. The GitHub release takes its notes from that section.
- CI builds the image on every pull request, scans it with Trivy (a fixable CRITICAL
  finding fails) and runs the new smoke test `tests/smoke-image.sh` on it.
- The publish workflow runs the same smoke test and pushes exactly the tested image,
  by digest from the local build cache, before it sets the tags.
- Align the repository with the shared baseline: CI jobs have time limits, the version
  bump pushes without stored credentials, a release run fails when the release exists
  already, and SonarCloud analyzes the tests as tests for Python 3.14.
- CI also reports fixable HIGH findings of the image scan: in the job summary, and on
  `main` in one tracking issue that closes once the image is clean. A fixable CRITICAL
  finding still fails the build.

### Security

- The image no longer ships pip. Nothing uses it at runtime, and the msgpack and
  setuptools it vendors carry fixable HIGH findings (GHSA-6v7p-g79w-8964,
  CVE-2025-47273).

## [0.8.0] - 2026-09-24

### Security

- Compare the bearer token in constant time.
- Compare the login user name as bytes, so a non-ASCII name gets 401, not 500.
- Log a warning at startup when the API runs without authentication.
- Audit the workflows with actionlint and zizmor in a new `lint` job.
- Lint the Dockerfile with Hadolint and `trivy config` in the `lint` job.
- Add the OpenSSF Scorecard workflow and its README badge.
- Limit the token permissions of every workflow.
- Stop persisting the checkout credentials.
- Pass template values to scripts through environment variables.
- Let Renovate pin GitHub Actions by commit digest.
- Let Renovate refresh `uv.lock` and raise OSV vulnerability alerts.
- Attest the published image: signed build provenance and an SPDX SBOM.
- Build the image from `uv.lock` with hashes, through a digest-pinned uv image.
- Attach the provenance bundle and the SBOM to the GitHub release as assets.

### Added

- CHANGELOG.md, and Verify, Contributing and Disclaimer sections in the README.

### Changed

- **Behavior change:** fail closed without authentication. With no `[api] token`
  and no complete `[auth]` section, `sb-ctrl serve` refuses to start, the app
  refuses to start under uvicorn, and every request gets 401. An install that
  runs without authentication on purpose must set `[api] allow_open = true`.
  It then starts with a warning. A non-boolean `allow_open` is a config error.
- Use neutral example hosts in the config defaults, the example config and the docs.
- Renovate takes its common rules from the shared preset `github>grigoriev/renovate-config`.

### Fixed

- Document the 400 answer of `POST /login` in the OpenAPI schema.
- Reject a transfer whose destination is not inside the library root, for example
  a name that sanitizes to nothing.
- Run CI once per commit on a Renovate branch: drop `renovate/**` from the push trigger.
