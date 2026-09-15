from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "install.py"
SOURCE = ROOT / "hermes_antigravity_acp.py"

spec = importlib.util.spec_from_file_location("adapter_installer", INSTALLER)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load installer module at {INSTALLER}")
installer = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = installer
spec.loader.exec_module(installer)


class InstallerTests(unittest.TestCase):
    def test_env_binding_preserves_existing_values_and_file_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            env_path = root / ".env"
            destination = root / "scripts" / "hermes-antigravity-acp"
            env_path.write_text(
                "EXISTING_SECRET=do-not-change\nHERMES_COPILOT_ACP_COMMAND=/old/path\n",
                encoding="utf-8",
            )
            env_path.chmod(0o640)

            installer.write_env_binding(env_path, destination)

            lines = env_path.read_text(encoding="utf-8").splitlines()
            self.assertIn("EXISTING_SECRET=do-not-change", lines)
            bindings = [
                line for line in lines if line.startswith("HERMES_COPILOT_ACP_COMMAND=")
            ]
            self.assertEqual(
                bindings,
                [f"HERMES_COPILOT_ACP_COMMAND={destination}"],
            )
            self.assertEqual(env_path.stat().st_mode & 0o777, 0o640)

    def test_failed_verification_restores_previous_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "source.py"
            destination = root / "adapter"
            source.write_text("new adapter\n", encoding="utf-8")
            destination.write_text("old adapter\n", encoding="utf-8")
            destination.chmod(0o700)

            def mismatched_destination_digest(path: Path) -> str:
                return (
                    "source-digest"
                    if path.resolve() == source.resolve()
                    else "mismatch"
                )

            with patch.object(
                installer, "digest", side_effect=mismatched_destination_digest
            ):
                return_code = installer.install(source, destination, dry_run=False)

            self.assertEqual(return_code, 1)
            self.assertEqual(destination.read_text(encoding="utf-8"), "old adapter\n")
            self.assertEqual(destination.stat().st_mode & 0o777, 0o700)

    def test_install_backs_up_existing_file_and_verifies_bytes_and_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            destination = root / "scripts" / "hermes-antigravity-acp"
            destination.parent.mkdir(parents=True)
            destination.write_text("old adapter\n", encoding="utf-8")
            destination.chmod(0o600)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(INSTALLER),
                    "--destination",
                    str(destination),
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(destination.read_bytes(), SOURCE.read_bytes())
            self.assertEqual(os.stat(destination).st_mode & 0o777, 0o700)
            backups = list(destination.parent.glob("hermes-antigravity-acp.bak-*"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(encoding="utf-8"), "old adapter\n")

            check = subprocess.run(
                [
                    sys.executable,
                    str(INSTALLER),
                    "--check",
                    "--destination",
                    str(destination),
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(check.returncode, 0, check.stderr)
            self.assertIn("MATCH", check.stdout)

            destination.write_text("drift\n", encoding="utf-8")
            drift = subprocess.run(
                [
                    sys.executable,
                    str(INSTALLER),
                    "--check",
                    "--destination",
                    str(destination),
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(drift.returncode, 1)
            self.assertIn("DRIFT", drift.stdout)


if __name__ == "__main__":
    unittest.main()
