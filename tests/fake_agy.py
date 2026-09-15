#!/usr/bin/env python3
"""Deterministic stream-json stand-in used by the adapter test suite."""

from __future__ import annotations

import json
import os
import re
import signal
import sys
import time
import uuid
from pathlib import Path

RUNNING = True


def _stop(_signum: int, _frame: object) -> None:
    global RUNNING
    RUNNING = False


signal.signal(signal.SIGTERM, _stop)
signal.signal(signal.SIGINT, _stop)

counter_path = os.environ.get("FAKE_AGY_START_COUNT_FILE")
pid_path = os.environ.get("FAKE_AGY_PID_FILE")
argv_path = os.environ.get("FAKE_AGY_ARGV_FILE")
if counter_path:
    with Path(counter_path).open("a", encoding="utf-8") as handle:
        handle.write(f"{os.getpid()}\n")
if pid_path:
    Path(pid_path).write_text(str(os.getpid()), encoding="utf-8")
if argv_path:
    with Path(argv_path).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(sys.argv) + "\n")

conversation_id = str(uuid.uuid4())
print(
    json.dumps(
        {
            "event": "init",
            "conversation_id": conversation_id,
            "init": {"permission_mode": "always-proceed"},
        }
    ),
    flush=True,
)

for raw_line in sys.stdin:
    if not RUNNING:
        break
    try:
        request = json.loads(raw_line)
        content = str(((request.get("message") or {}).get("content") or ""))
    except Exception:
        continue

    if "--conversation" in sys.argv:
        resume_delay = float(os.environ.get("FAKE_AGY_DELAY_ON_RESUME_SECONDS", "0"))
        if resume_delay > 0:
            time.sleep(resume_delay)

    if "FAKE_HANG_BEFORE_TEXT" in content:
        while RUNNING:
            time.sleep(0.05)
        break

    if "FAKE_TOOL_CALL" in content:
        response = (
            '<tool_call>{"id":"call_fake","type":"function",'
            '"function":{"name":"read_file",'
            '"arguments":"{\\"path\\":\\"README.md\\"}"}}</tool_call>'
        )
    else:
        markers = re.findall(r"FAKE_REPLY:([A-Z0-9_]+)", content)
        response = markers[-1] if markers else "FAKE_OK"

    midpoint = max(1, len(response) // 2)
    for index, chunk in enumerate((response[:midpoint], response[midpoint:])):
        if not chunk:
            continue
        print(
            json.dumps(
                {
                    "event": "step_update",
                    "step_update": {
                        "conversation_id": conversation_id,
                        "step_index": index + 1,
                        "state": "ACTIVE" if index == 0 else "DONE",
                        "step_type": "agent_response",
                        "text_delta": chunk,
                    },
                }
            ),
            flush=True,
        )

    print(
        json.dumps(
            {
                "event": "result",
                "result": {"status": "SUCCESS", "response": response},
            }
        ),
        flush=True,
    )
    if os.environ.get("FAKE_AGY_EXIT_AFTER_TURN") == "1":
        break
