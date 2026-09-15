# Maintainers

The project is maintained by the operator of this GitHub account. Pull
requests, issues, and security reports are reviewed asynchronously.

## Release checklist (operator-only)

1. Update `CHANGELOG.md` with a dated heading for the new version.
2. Confirm `hermes_antigravity_acp.VERSION` matches the CHANGELOG heading.
3. Run the full local quality gate and the live OAuth smoke test.
4. Tag the release commit with an annotated `vX.Y.Z` tag.
5. Publish the GitHub Release from the tag using `gh release create`.
6. Verify that topics and the repository description are still accurate.
