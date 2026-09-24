# Changelog

All notable changes to this project are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
The project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security

- Audit the workflows with actionlint and zizmor in a new `lint` job.
- Lint the Dockerfile with Hadolint and `trivy config` in the `lint` job.
- Add the OpenSSF Scorecard workflow and its README badge.
- Limit the token permissions of every workflow.
- Stop persisting the checkout credentials.
- Pass template values to scripts through environment variables.
- Let Renovate pin GitHub Actions by commit digest.
- Let Renovate refresh `uv.lock` and raise OSV vulnerability alerts.
- Attest the published image: signed build provenance and an SPDX SBOM.

### Added

- CHANGELOG.md, and Verify, Contributing and Disclaimer sections in the README.

### Fixed

- Run CI once per commit on a Renovate branch: drop `renovate/**` from the push trigger.

Earlier releases are listed on the
[GitHub releases page](https://github.com/grigoriev/sb-ctrl/releases).
