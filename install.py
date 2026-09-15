#!/usr/bin/env python3
"""Rollback-safe installer for hermes-antigravity-acp."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SOURCE = Path(__file__).resolve().with_name("hermes_antigravity_acp.py")
DEFAULT_HERMES_HOME = Path(
    os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))
).expanduser()
DEFAULT_DESTINATION = DEFAULT_HERMES_HOME / "scripts" / "hermes-antigravity-acp"
ACP_COMMAND_KEY = "HERMES_COPILOT_ACP_COMMAND"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stop_existing_broker(destination: Path) -> None:
    if not destination.is_file():
        return
    try:
        subprocess.run(
            [sys.executable, str(destination), "--shutdown-broker"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def backup_path(destination: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    return destination.with_name(f"{destination.name}.bak-{timestamp}")


def _serialize_env_value(value: str) -> str:
    if value and not any(char.isspace() for char in value) and "#" not in value:
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def write_env_binding(env_path: Path, destination: Path) -> None:
    """Atomically update only the non-secret ACP command binding."""

    env_path = env_path.expanduser().resolve()
    env_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    original_mode = env_path.stat().st_mode & 0o777 if env_path.exists() else 0o600
    lines = (
        env_path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        if env_path.exists()
        else []
    )
    replacement = f"{ACP_COMMAND_KEY}={_serialize_env_value(str(destination))}"
    output: list[str] = []
    replaced = False
    for line in lines:
        candidate = line.strip()
        if candidate.startswith("export "):
            candidate = candidate[7:].lstrip()
        if candidate.startswith(f"{ACP_COMMAND_KEY}="):
            if not replaced:
                output.append(replacement)
                replaced = True
            continue
        output.append(line)
    if not replaced:
        output.append(replacement)

    fd, temporary_name = tempfile.mkstemp(
        prefix=".env_",
        suffix=".tmp",
        dir=str(env_path.parent),
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("\n".join(output) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(original_mode)
        os.replace(temporary, env_path)
    finally:
        temporary.unlink(missing_ok=True)


def resolve_hermes_env_path() -> Path:
    hermes = shutil.which("hermes")
    if not hermes:
        raise RuntimeError("Hermes CLI not found; cannot resolve active profile .env")
    completed = subprocess.run(
        [hermes, "config", "env-path"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        check=False,
    )
    value = completed.stdout.strip()
    if completed.returncode != 0 or not value:
        raise RuntimeError(
            "Cannot resolve Hermes profile .env: "
            + (completed.stderr.strip() or f"exit {completed.returncode}")
        )
    return Path(value)


def install(
    source: Path,
    destination: Path,
    *,
    dry_run: bool,
    configure_hermes: bool = False,
) -> int:
    source = source.resolve()
    destination = destination.expanduser().resolve()
    if not source.is_file():
        print(f"ERROR source missing: {source}", file=sys.stderr)
        return 2
    if source == destination:
        print("ERROR source and destination are the same file", file=sys.stderr)
        return 2

    source_hash = digest(source)
    existing = destination.is_file()
    original_mode = destination.stat().st_mode & 0o777 if existing else None
    backup = backup_path(destination) if existing else None
    if dry_run:
        print(f"DRY_RUN source_sha256={source_hash}")
        print(f"DRY_RUN destination={destination}")
        print(f"DRY_RUN backup={backup if backup is not None else 'none'}")
        return 0

    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    stop_existing_broker(destination)
    if backup is not None:
        shutil.copy2(destination, backup)
        backup.chmod(0o600)

    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        dir=str(destination.parent),
    )
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        shutil.copyfile(source, temporary)
        temporary.chmod(0o700)
        os.replace(temporary, destination)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass

    installed_hash = digest(destination)
    installed_mode = destination.stat().st_mode & 0o777
    if installed_hash != source_hash or installed_mode != 0o700:
        print(
            "ERROR install verification failed: "
            f"sha_match={installed_hash == source_hash} mode={installed_mode:o}",
            file=sys.stderr,
        )
        try:
            if backup is not None and original_mode is not None:
                rollback_fd, rollback_name = tempfile.mkstemp(
                    prefix=f".{destination.name}.rollback.",
                    dir=str(destination.parent),
                )
                os.close(rollback_fd)
                rollback = Path(rollback_name)
                try:
                    shutil.copyfile(backup, rollback)
                    rollback.chmod(original_mode)
                    os.replace(rollback, destination)
                finally:
                    try:
                        rollback.unlink()
                    except FileNotFoundError:
                        pass
                print(f"ROLLBACK restored={destination}", file=sys.stderr)
            else:
                destination.unlink(missing_ok=True)
                print("ROLLBACK removed unverified new destination", file=sys.stderr)
        except Exception as exc:
            print(f"ROLLBACK FAILED: {exc}", file=sys.stderr)
            return 2
        return 1

    print(f"INSTALLED sha256={installed_hash} mode=700 destination={destination}")
    if backup is not None:
        print(f"BACKUP {backup}")
    if configure_hermes:
        try:
            env_path = resolve_hermes_env_path()
            write_env_binding(env_path, destination)
        except Exception as exc:
            print(f"ERROR Hermes binding failed: {exc}", file=sys.stderr)
            return 2
        print(f"CONFIGURED {ACP_COMMAND_KEY} in {env_path}")
    return 0


def check(source: Path, destination: Path) -> int:
    source = source.resolve()
    destination = destination.expanduser().resolve()
    if not source.is_file():
        print(f"ERROR source missing: {source}", file=sys.stderr)
        return 2
    if not destination.is_file():
        print(f"DRIFT destination missing: {destination}")
        return 1

    source_hash = digest(source)
    destination_hash = digest(destination)
    mode = destination.stat().st_mode & 0o777
    matched = source_hash == destination_hash and mode == 0o700
    label = "MATCH" if matched else "DRIFT"
    print(
        f"{label} source_sha256={source_hash} destination_sha256={destination_hash} "
        f"mode={mode:o}"
    )
    return 0 if matched else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--configure-hermes",
        action="store_true",
        help="Persist the non-secret ACP command in the active Hermes profile",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.check:
        return check(args.source, args.destination)
    return install(
        args.source,
        args.destination,
        dry_run=args.dry_run,
        configure_hermes=args.configure_hermes,
    )


if __name__ == "__main__":
    raise SystemExit(main())
