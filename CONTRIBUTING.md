# Contributing

Thank you for your interest in improving hermes-antigravity-acp. This
document describes how to set up a development environment, run the test
suite, and submit a change.

## Local setup

```bash
git clone https://github.com/taras-polishchuk/hermes-antigravity-acp.git
cd hermes-antigravity-acp
python3 -m pip install --user ruff==0.15.22 mypy==1.13.0 bandit==1.9.4
PYTHONWARNINGS=error::ResourceWarning python3 -m unittest discover -s tests -v
```

## Development discipline

- Run the full test suite with `PYTHONWARNINGS=error::ResourceWarning`
  before opening a pull request.
- Run `ruff format`, `ruff check`, and `mypy` before requesting review.
- New behaviour must include a test. Bug fixes must include a
  reproduction test.
- Do not commit `.env`, OAuth tokens, Antigravity conversation databases,
  or runtime socket files. The `.gitignore` covers most of these, but
  staged-diff review is non-negotiable.

## Branch and commit workflow

1. Branch off `main`.
2. Use conventional commit prefixes (`feat:`, `fix:`, `docs:`, `refactor:`
   `test:`, `chore:`).
3. Keep changes minimal. One concern per pull request.
4. Add an entry to `CHANGELOG.md` under `## Unreleased` for any user-facing
   change.

## Pull request expectations

- Include a clear description of the problem and the proposed solution.
- Reference the relevant section of `README.md`, `ARCHITECTURE.md`,
  `TROUBLESHOOTING.md` or `SECURITY.md` if the change touches one of
  those contracts.
- Do not open a draft pull request that bumps the version or the changelog
  release date; those are operator-authorized steps at release time.

## Releases

- Releases are tagged from `main` by the maintainer. Tags follow strict
  semver: `vX.Y.Z`.
- The PyPI publication is fully automated through GitHub Actions
  Trusted Publishing. Pushing a tag `v*.*.*` triggers the
  `release.yml` workflow, which builds sdist + wheel, runs no tests
  (the `ci.yml` workflow already gates `main`), and uploads both
  artifacts to PyPI and TestPyPI through OIDC. No API token is ever
  stored in the repository.
- The CHANGELOG release heading `## X.Y.Z - YYYY-MM-DD` is set at release
  time, not when changes are merged.
- PyPI does not allow overwriting a released version. To fix a published
  bug, cut a new version (e.g. `2.1.1`). To retire a release, use the
  PyPI web UI to yank it; do not delete the Git tag.

## Code of conduct

Be respectful. Stay on-topic. Cite evidence.
