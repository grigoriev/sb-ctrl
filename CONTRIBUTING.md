# Contributing

Issues and pull requests are welcome.

## Build and test

```sh
uv sync --all-extras                           # install the dependencies
uv run ruff check .                            # lint
uv run ruff format --check .                   # format check
uv run mypy sb_ctrl tests                      # type check
uv run pytest --cov --cov-report=term-missing  # tests with coverage
docker build -t sb-ctrl:test .                 # build the image
tests/smoke-image.sh sb-ctrl:test              # start the image and check the API
```

On an ARM machine, build with `--platform linux/amd64`; the smoke test then runs the image on
that platform.

CI runs ShellCheck, Hadolint, actionlint, zizmor, `trivy config`, ruff, mypy, the tests,
SonarCloud, and builds the image, scans it with Trivy and runs the smoke test on it for every
pull request. A fixable CRITICAL finding fails the build. Fixable HIGH findings go to one
tracking issue, updated on each push to `main` and closed once the image is clean.

## Pull requests

1. Branch from the default branch as `type/description`, for example `fix/empty-title`.
2. Keep one change per pull request. New behavior comes with tests; a bug fix adds a test that
   fails without it.
3. Write commit messages as [Conventional Commits](https://www.conventionalcommits.org/) without a
   scope: `feat: ...`, `fix: ...`, `docs: ...`, `refactor: ...`, `test: ...`, `build: ...`,
   `ci: ...`, `chore: ...`.
4. Sign your commits. The default branch accepts verified signatures only.
5. Add an entry under `## [Unreleased]` in `CHANGELOG.md`, written for users: the release notes
   quote it. Update the README when behavior or configuration changes.

Pull requests are squash-merged once all required checks are green.

## Releases

A maintainer runs the Bump Version workflow. It moves the Unreleased entries into a versioned
section and tags the release. The Publish image workflow builds the image, runs the smoke test,
pushes exactly the tested image and creates the GitHub release with signed build provenance and
the SBOM.
