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
3. Verify topics and the repository description are still accurate.
4. TestPyPI is a dry-run surface. To enable it, add a trusted publisher
   at <https://test.pypi.org/manage/account/publishing/> with these
   exact values:
   - **Owner**: `taras-polishchuk`
   - **Project**: `hermes-antigravity-acp`
   - **Repository**: `taras-polishchuk/hermes-antigravity-acp`
   - **Workflow filename**: `release.yml`
   - **Environment name**: `testpypi`
   After that, re-trigger the workflow with
   `gh workflow run release.yml --ref vX.Y.Z --repo taras-polishchuk/hermes-antigravity-acp`
   to populate TestPyPI for the chosen tag. TestPyPI failures do NOT
   block the workflow conclusion (`continue-on-error: true`).
