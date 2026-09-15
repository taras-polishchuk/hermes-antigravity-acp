# Maintainers

The project is maintained by the operator of this GitHub account. Pull
requests, issues, and security reports are reviewed asynchronously.

## Release checklist (operator-only)

1. Confirm `hermes_antigravity_acp.VERSION`, `pyproject.toml`'s `version`,
   and `CHANGELOG.md` heading all match `vX.Y.Z`.
2. Confirm the local install and the offline test suite pass.
3. Push the `vX.Y.Z` annotated tag; the `release.yml` workflow publishes
   to PyPI through GitHub Trusted Publishing. No API token is required
   once the trusted publisher is registered on PyPI for this repo.
4. Edit the GitHub Release description if the auto-generated notes miss
   anything user-facing.
5. Verify topics and the repository description are still accurate.
6. If a PyPI trusted publisher has never been registered for this repo,
   add it once at <https://pypi.org/manage/account/publishing/>:
   owner `taras-polishchuk`, project `hermes-antigravity-acp`,
   repository `taras-polishchuk/hermes-antigravity-acp`, workflow
   filename `release.yml`, environment name `pypi`.
