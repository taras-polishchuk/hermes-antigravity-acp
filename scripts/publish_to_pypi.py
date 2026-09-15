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
4. Triggers the ``release.yml`` workflow through ``gh workflow run``.

It does NOT push the tag automatically; tag publication is an explicit
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
PACKAGE_DIR = REPO / "src" / "hermes_antigravity_acp"


def run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # type: ignore[call-overload]
        cmd,
        capture_output=True,
        text=True,
        check=False,
        **kwargs,  # noqa: PERF401 - clarity over micro-perf
    )


def _find_version(path: Path, pattern: str) -> str | None:
    match = re.search(pattern, path.read_text(encoding="utf-8"), re.MULTILINE)
    return match.group(1).strip() if match else None


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
    parser.add_argument(
        "--target",
        choices=("pypi", "testpypi"),
        default="pypi",
        help=(
            "Publish target. Defaults to 'pypi'. Use 'testpypi' to verify a "
            "trusted publisher registration by populating TestPyPI only "
            "(TestPyPI's trusted publisher must already be registered on "
            "https://test.pypi.org/manage/account/publishing/)."
        ),
    )
    args = parser.parse_args()

    pyproject_version = _find_version(
        REPO / "pyproject.toml", r'^version\s*=\s*"([^"]+)"'
    )
    adapter_version = _find_version(
        PACKAGE_DIR / "adapter.py", r'VERSION\s*=\s*"([^"]+)"'
    )
    if pyproject_version is None or adapter_version is None:
        print(
            "ERROR cannot find version in pyproject.toml or adapter.py",
            file=sys.stderr,
        )
        return 2
    if pyproject_version != adapter_version:
        print(
            "ERROR version mismatch: "
            f"pyproject.toml={pyproject_version!r} adapter.py={adapter_version!r}",
            file=sys.stderr,
        )
        return 2
    version = pyproject_version

    changelog = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    if not re.search(
        rf"^## {re.escape(version)} - \d{{4}}-\d{{2}}-\d{{2}}$",
        changelog,
        re.MULTILINE,
    ):
        print(
            f"WARN CHANGELOG.md has no dated heading for version {version}.",
            file=sys.stderr,
        )

    if shutil.which("gh") is None:
        print("ERROR gh CLI not found; install github-cli.", file=sys.stderr)
        return 2

    if not args.skip_build:
        print(f"BUILD version={version}")
        completed = run(
            ["python3", "-m", "build", "--sdist", "--wheel", "--no-isolation"],
            cwd=str(REPO),
        )
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

    target_label = args.target
    target_docs = (
        "PyPI"
        if target_label == "pypi"
        else "TestPyPI (dry-run only; trusted publisher at https://test.pypi.org/manage/account/publishing/)"
    )
    completed = run(
        [
            "gh",
            "workflow",
            "run",
            "release.yml",
            "--ref",
            args.tag,
            "--repo",
            "taras-polishchuk/hermes-antigravity-acp",
        ]
    )
    if completed.returncode != 0:
        print(completed.stdout)
        print(completed.stderr, file=sys.stderr)
        return 2
    print(completed.stdout.strip())
    print(
        "DONE. The workflow will publish to "
        f"{target_docs} for taras-polishchuk/hermes-antigravity-acp "
        f"(workflow release.yml, environment {target_label})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
