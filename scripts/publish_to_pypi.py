#!/usr/bin/env python3
"""Publish hermes-antigravity-acp to PyPI through Trusted Publishing.

This script is a thin convenience wrapper. The actual upload happens
through GitHub Actions OIDC, which requires a one-time trusted publisher
registration at <https://pypi.org/manage/account/publishing/>:

- Owner: ``taras-polishchuk``
- Project: ``hermes-antigravity-acp``
- Repository: ``taras-polishchuk/hermes-antigravity-acp``
- Workflow filename: ``release.yml``
- Environment name: ``pypi``

The TestPyPI equivalent lives at
<https://test.pypi.org/manage/account/publishing/> with environment name
``testpypi``.

Once the trusted publisher is registered (one-time setup, ~30 seconds),
re-running this script will publish without any further operator action.
The script:

1. Verifies the local version string matches ``pyproject.toml`` and the
   ``CHANGELOG.md`` heading.
2. Builds sdist and wheel into ``dist/``.
3. Validates both artifacts via ``twine check``.
4. Prompts for the Git tag to publish (default ``HEAD``).
5. Triggers the ``release.yml`` workflow through ``gh workflow run``.

It does NOT push the tag automatically — tag publication is an explicit
operator step.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=False, **kwargs)  # noqa: PERF401 - clarity over micro-perf


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tag",
        default="HEAD",
        help="Git tag or ref to publish (default HEAD). The tag must already exist on origin.",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Skip local sdist + wheel build (use existing dist/).",
    )
    args = parser.parse_args()

    pkg_dir = REPO / "src" / "hermes_antigravity_acp"
    pyproject = REPO / "pyproject.toml"
    version = (
        re.search(r'^version\s*=\s*"([^"]+)"', pyproject.read_text(encoding="utf-8"), re.MULTILINE)
        .group(1)
        .strip()
    )
    adapter_version = pkg_dir.joinpath("adapter.py").read_text(encoding="utf-8")
    adapter_match = re.search(r'VERSION\s*=\s*"([^"]+)"', adapter_version)
    if adapter_match is None or adapter_match.group(1) != version:
        print(
            f"ERROR version mismatch: pyproject.toml={version!r} adapter.py="
            f"{adapter_match.group(1) if adapter_match else 'MISSING'!r}",
            file=sys.stderr,
        )
        return 2

    changelog = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    if not re.search(rf"^## {re.escape(version)} - \d{{4}}-\d{{2}}-\d{{2}}$", changelog, re.MULTILINE):
        print(
            f"WARN CHANGELOG.md has no dated heading for version {version}.",
            file=sys.stderr,
        )

    if shutil.which("gh") is None:
        print("ERROR gh CLI not found; install github-cli.", file=sys.stderr)
        return 2

    if not args.skip_build:
        print(f"BUILD version={version}")
        completed = run(["python3", "-m", "build", "--sdist", "--wheel", "--no-isolation"], cwd=str(REPO))
        if completed.returncode != 0:
            print(completed.stdout)
            print(completed.stderr, file=sys.stderr)
            return 2

    dist = REPO / "dist"
    artifacts = sorted(dist.glob("*"))
    if not artifacts:
        print(f"ERROR no artifacts in {dist}", file=sys.stderr)
        return 2
    print(f"ARTIFACTS {[a.name for a in artifacts]}")

    completed = run(["python3", "-m", "twine", "check", *[str(a) for a in artifacts]])
    if completed.returncode != 0:
        print(completed.stdout)
        print(completed.stderr, file=sys.stderr)
        return 2
    print("TWINE_OK")

    completed = run(
        ["gh", "workflow", "run", "release.yml", "--ref", args.tag, "--repo", "taras-polishchuk/hermes-antigravity-acp"],
    )
    if completed.returncode != 0:
        print(completed.stdout)
        print(completed.stderr, file=sys.stderr)
        return 2
    print(completed.stdout.strip())
    print(
        "DONE. The workflow will publish to PyPI once the one-time trusted publisher is "
        "registered at <https://pypi.org/manage/account/publishing/> for "
        "taras-polishchuk/hermes-antigravity-acp (workflow release.yml, environment pypi)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
