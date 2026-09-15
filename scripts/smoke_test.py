#!/usr/bin/env python3
"""Run an isolated two-turn live OAuth smoke test against the adapter."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ADAPTER = ROOT / "hermes_antigravity_acp.py"


def exchange(adapter: Path, env: dict[str, str], marker: str) -> dict[str, Any]:
    process = subprocess.Popen(
        [sys.executable, str(adapter)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(ROOT),
        env=env,
    )
    if process.stdin is None or process.stdout is None or process.stderr is None:
        process.kill()
        raise RuntimeError("Adapter did not expose stdio pipes")

    started = time.monotonic()
    for message in (
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "session/new",
            "params": {"cwd": str(ROOT), "mcpServers": []},
        },
    ):
        process.stdin.write(json.dumps(message) + "\n")
        process.stdin.flush()

    initialize_result = json.loads(process.stdout.readline())
    session_result = json.loads(process.stdout.readline())
    session_id = session_result["result"]["sessionId"]
    prompt = "\n\n".join(
        (
            "You are being used as the active ACP agent backend for Hermes.",
            f"Hermes requested model hint: {env['SMOKE_MODEL']}",
            f"User:\nReply with exactly {marker} and nothing else.",
        )
    )
    process.stdin.write(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "session/prompt",
                "params": {
                    "sessionId": session_id,
                    "prompt": [{"type": "text", "text": prompt}],
                },
            }
        )
        + "\n"
    )
    process.stdin.flush()

    chunks: list[str] = []
    prompt_result: dict[str, Any] | None = None
    while True:
        raw = process.stdout.readline()
        if not raw:
            break
        item = json.loads(raw)
        if item.get("method") == "session/update":
            text = str(
                (
                    (
                        ((item.get("params") or {}).get("update") or {}).get("content")
                        or {}
                    ).get("text")
                    or ""
                )
            )
            chunks.append(text)
        if item.get("id") == 3:
            prompt_result = item
            break

    elapsed = time.monotonic() - started
    process.stdin.close()
    stderr = process.stderr.read()
    return_code = process.wait(timeout=5)
    process.stdout.close()
    process.stderr.close()

    return {
        "marker": marker,
        "elapsed_seconds": round(elapsed, 3),
        "text": "".join(chunks),
        "return_code": return_code,
        "prompt_error": prompt_result.get("error")
        if prompt_result
        else "missing result",
        "stderr_line_count": len(stderr.splitlines()),
        "initialize_ok": initialize_result.get("id") == 1,
    }


def adapter_json(
    adapter: Path, env: dict[str, str], flag: str
) -> tuple[int, dict[str, Any]]:
    completed = subprocess.run(
        [sys.executable, str(adapter), flag],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    payload = json.loads(completed.stdout) if completed.stdout.strip() else {}
    return completed.returncode, payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", type=Path, default=DEFAULT_ADAPTER)
    parser.add_argument("--model", default="gemini-3.1-pro-high")
    parser.add_argument("--max-cold-seconds", type=float, default=15.0)
    parser.add_argument("--max-warm-seconds", type=float, default=15.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    adapter = args.adapter.expanduser().resolve()
    if not adapter.is_file():
        print(json.dumps({"ok": False, "error": f"adapter missing: {adapter}"}))
        return 2

    with tempfile.TemporaryDirectory(prefix="hermes-antigravity-smoke-") as tmpdir:
        env = os.environ.copy()
        env.update(
            {
                "HERMES_ANTIGRAVITY_RUNTIME_DIR": str(Path(tmpdir) / "runtime"),
                "HERMES_SESSION_ID": f"smoke-{uuid.uuid4()}",
                "ANTIGRAVITY_FIRST_TEXT_TIMEOUT": str(args.max_cold_seconds),
                "ANTIGRAVITY_STALL_TIMEOUT": "30",
                "ANTIGRAVITY_PRINT_TIMEOUT": "60",
                "ANTIGRAVITY_SESSION_IDLE_TIMEOUT": "120",
                "ANTIGRAVITY_BROKER_IDLE_TIMEOUT": "180",
                "SMOKE_MODEL": args.model,
            }
        )

        results: list[dict[str, Any]] = []
        status_one: dict[str, Any] = {}
        status_two: dict[str, Any] = {}
        backend_pids: list[int] = []
        try:
            results.append(exchange(adapter, env, "OAUTH_SMOKE_ONE"))
            status_one_rc, status_one = adapter_json(adapter, env, "--status")
            results.append(exchange(adapter, env, "OAUTH_SMOKE_TWO"))
            status_two_rc, status_two = adapter_json(adapter, env, "--status")
            backend_pids = list(status_two.get("backend_pids") or [])
        finally:
            shutdown = subprocess.run(
                [sys.executable, str(adapter), "--shutdown-broker"],
                cwd=str(ROOT),
                env=env,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                alive = [pid for pid in backend_pids if Path(f"/proc/{pid}").exists()]
                if not alive:
                    break
                time.sleep(0.05)
            alive_after_shutdown = [
                pid for pid in backend_pids if Path(f"/proc/{pid}").exists()
            ]

        same_pid = (
            status_one.get("backend_pids") == status_two.get("backend_pids")
            and len(status_one.get("backend_pids") or []) == 1
        )
        checks = {
            "markers": [item["text"].strip() for item in results]
            == ["OAUTH_SMOKE_ONE", "OAUTH_SMOKE_TWO"],
            "adapter_return_codes": all(item["return_code"] == 0 for item in results),
            "prompt_errors": all(item["prompt_error"] is None for item in results),
            "status_return_codes": status_one_rc == 0 and status_two_rc == 0,
            "same_backend_pid": same_pid,
            "cold_latency": results[0]["elapsed_seconds"] <= args.max_cold_seconds,
            "warm_latency": results[1]["elapsed_seconds"] <= args.max_warm_seconds,
            "shutdown_return_code": shutdown.returncode == 0,
            "backend_reaped": not alive_after_shutdown,
        }
        report = {
            "ok": all(checks.values()),
            "model": args.model,
            "checks": checks,
            "turns": results,
            "session_counts": [
                status_one.get("session_count"),
                status_two.get("session_count"),
            ],
            "backend_pids_alive_after_shutdown": alive_after_shutdown,
        }
        print(json.dumps(report, indent=2, ensure_ascii=True))
        return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
