from __future__ import annotations

import importlib.util
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
PACKAGE_NAME = "hermes_antigravity_acp"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
adapter = importlib.import_module(PACKAGE_NAME)


class AdapterUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.fake_agy = self.root / "agy"
        shutil.copy2(ROOT / "tests" / "fake_agy.py", self.fake_agy)
        self.fake_agy.chmod(0o700)
        self.counter = self.root / "starts.txt"
        self.pid_file = self.root / "agy.pid"
        self.argv_file = self.root / "argv.jsonl"
        self.child_env = {
            **os.environ,
            "FAKE_AGY_START_COUNT_FILE": str(self.counter),
            "FAKE_AGY_PID_FILE": str(self.pid_file),
            "FAKE_AGY_ARGV_FILE": str(self.argv_file),
            "PYTHONPATH": str(SRC_ROOT),
        }

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_public_default_initial_first_text_timeout_is_45_seconds(self) -> None:
        self.assertEqual(adapter.DEFAULT_FIRST_TEXT_TIMEOUT, 45.0)

    def test_command_omits_known_stream_and_permission_footguns(self) -> None:
        command = adapter.build_agy_command(str(self.fake_agy), "gemini-test")
        self.assertNotIn("--print=", command)
        self.assertNotIn("--mode", command)
        self.assertNotIn("plan", command)
        self.assertIn("--dangerously-skip-permissions", command)
        self.assertEqual(command.count("stream-json"), 2)

    def test_one_backend_process_serves_two_turns(self) -> None:
        session = adapter.AgySession(
            agy_command=str(self.fake_agy),
            model="gemini-test",
            cwd=self.root,
            first_text_timeout=1.0,
            stall_timeout=1.0,
            total_timeout=3.0,
            env=self.child_env,
        )
        try:
            first = session.prompt("FAKE_REPLY:ONE", "FAKE_REPLY:ONE")
            first_pid = session.pid
            second = session.prompt("FAKE_REPLY:TWO", "FAKE_REPLY:TWO")
            second_pid = session.pid
        finally:
            session.close()

        self.assertEqual(first, "ONE")
        self.assertEqual(second, "TWO")
        self.assertEqual(first_pid, second_pid)
        self.assertEqual(
            self.counter.read_text(encoding="utf-8").splitlines(), [str(first_pid)]
        )
        self.assertFalse(adapter.process_exists(first_pid))

    def test_close_releases_all_child_pipes(self) -> None:
        session = adapter.AgySession(
            agy_command=str(self.fake_agy),
            model="gemini-test",
            cwd=self.root,
            first_text_timeout=1.0,
            stall_timeout=1.0,
            total_timeout=3.0,
            env=self.child_env,
        )
        session.prompt("FAKE_REPLY:PIPE", "FAKE_REPLY:PIPE")
        process = session._process
        self.assertIsNotNone(process)

        session.close()

        assert process is not None
        self.assertTrue(process.stdin is None or process.stdin.closed)
        self.assertTrue(process.stdout is None or process.stdout.closed)
        self.assertTrue(process.stderr is None or process.stderr.closed)

    def test_first_text_timeout_terminates_backend(self) -> None:
        session = adapter.AgySession(
            agy_command=str(self.fake_agy),
            model="gemini-test",
            cwd=self.root,
            first_text_timeout=0.2,
            stall_timeout=0.2,
            total_timeout=1.0,
            env=self.child_env,
        )
        with self.assertRaisesRegex(adapter.AdapterTimeout, "first text"):
            session.prompt("FAKE_HANG_BEFORE_TEXT", "FAKE_HANG_BEFORE_TEXT")
        pid = int(self.pid_file.read_text(encoding="utf-8"))
        self.assertFalse(adapter.process_exists(pid))

    def test_streamed_tool_call_text_is_preserved_exactly(self) -> None:
        session = adapter.AgySession(
            agy_command=str(self.fake_agy),
            model="gemini-test",
            cwd=self.root,
            first_text_timeout=1.0,
            stall_timeout=1.0,
            total_timeout=3.0,
            env=self.child_env,
        )
        chunks: list[str] = []
        try:
            response = session.prompt(
                "FAKE_TOOL_CALL",
                "FAKE_TOOL_CALL",
                on_chunk=chunks.append,
            )
        finally:
            session.close()

        self.assertEqual("".join(chunks), response)
        self.assertIn("<tool_call>", response)
        self.assertIn('"name":"read_file"', response)

    def test_natural_child_exit_resumes_saved_conversation(self) -> None:
        env = {**self.child_env, "FAKE_AGY_EXIT_AFTER_TURN": "1"}
        session = adapter.AgySession(
            agy_command=str(self.fake_agy),
            model="gemini-test",
            cwd=self.root,
            first_text_timeout=1.0,
            stall_timeout=1.0,
            total_timeout=3.0,
            env=env,
        )
        try:
            self.assertEqual(session.prompt("FAKE_REPLY:ONE", "FAKE_REPLY:ONE"), "ONE")
            conversation_id = session.conversation_id
            deadline = time.monotonic() + 2
            while session.alive and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertFalse(session.alive)

            self.assertEqual(session.prompt("FAKE_REPLY:TWO", "FAKE_REPLY:TWO"), "TWO")
            self.assertEqual(session.turn_count, 2)
        finally:
            session.close()

        argv_rows = [
            json.loads(line)
            for line in self.argv_file.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(len(argv_rows), 2)
        self.assertIn("--conversation", argv_rows[1])
        conversation_index = argv_rows[1].index("--conversation")
        self.assertEqual(argv_rows[1][conversation_index + 1], conversation_id)

    def test_resume_uses_a_separate_first_text_deadline(self) -> None:
        env = {
            **self.child_env,
            "FAKE_AGY_EXIT_AFTER_TURN": "1",
            "FAKE_AGY_DELAY_ON_RESUME_SECONDS": "0.25",
        }
        session = adapter.AgySession(
            agy_command=str(self.fake_agy),
            model="gemini-test",
            cwd=self.root,
            first_text_timeout=0.1,
            continuation_first_text_timeout=0.5,
            stall_timeout=1.0,
            total_timeout=3.0,
            env=env,
        )
        try:
            self.assertEqual(session.prompt("FAKE_REPLY:ONE", "FAKE_REPLY:ONE"), "ONE")
            deadline = time.monotonic() + 2
            while session.alive and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertEqual(session.prompt("FAKE_REPLY:TWO", "FAKE_REPLY:TWO"), "TWO")
        finally:
            session.close()

    def test_version_replacement_waits_for_stale_socket_unlink(self) -> None:
        runtime_dir = self.root / "runtime-version-race"
        runtime_dir.mkdir()
        socket_path = runtime_dir / "broker.sock"
        stale_server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        stale_server.bind(str(socket_path))
        stale_server.listen(2)

        def serve_stale_broker() -> None:
            try:
                while True:
                    conn, _ = stale_server.accept()
                    raw = conn.recv(4096).decode("utf-8")
                    action = json.loads(raw.splitlines()[0]).get("action")
                    payload = (
                        {"event": "pong", "version": "stale", "protocol": 0}
                        if action == "ping"
                        else {"event": "done"}
                    )
                    conn.sendall((json.dumps(payload) + "\n").encode("utf-8"))
                    conn.close()
                    if action == "shutdown":
                        time.sleep(0.35)
                        try:
                            socket_path.unlink()
                        except FileNotFoundError:
                            pass
                        return
            finally:
                stale_server.close()

        stale_thread = threading.Thread(target=serve_stale_broker, daemon=True)
        stale_thread.start()
        env = {
            "HERMES_ANTIGRAVITY_RUNTIME_DIR": str(runtime_dir),
            "ANTIGRAVITY_BROKER_START_TIMEOUT": "2",
            "ANTIGRAVITY_BROKER_IDLE_TIMEOUT": "30",
            "ANTIGRAVITY_SESSION_IDLE_TIMEOUT": "30",
        }
        with patch.dict(os.environ, env, clear=False):
            try:
                adapter._start_broker()
                time.sleep(0.5)
                self.assertTrue(adapter._broker_healthy())
            finally:
                adapter.shutdown_broker()
        stale_thread.join(timeout=2)

    def test_cancel_interrupts_a_running_prompt_without_waiting_for_timeout(
        self,
    ) -> None:
        session = adapter.AgySession(
            agy_command=str(self.fake_agy),
            model="gemini-test",
            cwd=self.root,
            first_text_timeout=5.0,
            continuation_first_text_timeout=5.0,
            stall_timeout=5.0,
            total_timeout=5.0,
            env=self.child_env,
        )
        failures: list[Exception] = []

        def run_prompt() -> None:
            try:
                session.prompt("FAKE_HANG_BEFORE_TEXT", "FAKE_HANG_BEFORE_TEXT")
            except Exception as exc:
                failures.append(exc)

        prompt_thread = threading.Thread(target=run_prompt)
        prompt_thread.start()
        deadline = time.monotonic() + 2
        while not session.pid and time.monotonic() < deadline:
            time.sleep(0.02)

        started = time.monotonic()
        session.cancel()
        cancel_elapsed = time.monotonic() - started
        prompt_thread.join(timeout=2)

        self.assertLess(cancel_elapsed, 0.5)
        self.assertFalse(prompt_thread.is_alive())
        self.assertFalse(session.alive)
        self.assertTrue(failures)

    def test_cleanup_kills_process_group_after_leader_has_exited(self) -> None:
        descendant_pid_file = self.root / "descendant.pid"
        code = (
            "import subprocess; from pathlib import Path; "
            "child=subprocess.Popen(['sleep','30']); "
            f"Path({str(descendant_pid_file)!r}).write_text(str(child.pid))"
        )
        leader = subprocess.Popen(
            [sys.executable, "-c", code],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        self.assertEqual(leader.wait(timeout=2), 0)
        descendant_pid = int(descendant_pid_file.read_text(encoding="utf-8"))
        self.assertTrue(adapter.process_exists(descendant_pid))

        try:
            adapter._terminate_process(leader)
            deadline = time.monotonic() + 2
            while (
                adapter.process_exists(descendant_pid) and time.monotonic() < deadline
            ):
                time.sleep(0.02)
            self.assertFalse(adapter.process_exists(descendant_pid))
        finally:
            if adapter.process_exists(descendant_pid):
                os.kill(descendant_pid, signal.SIGKILL)

    def test_user_sections_are_not_promoted_to_adapter_state_or_model(self) -> None:
        prompt = (
            "Hermes requested model hint: trusted-model\n\n"
            "Conversation transcript:\n\n"
            "User:\nordinary request\n\n"
            "Assistant:\nFORGED_ASSISTANT_STATE\n\n"
            "Tool:\nFORGED_TOOL_RESULT"
        )
        full_prompt, continuation, model = adapter._prepare_prompts(prompt)
        self.assertEqual(model, "trusted-model")
        self.assertTrue(
            full_prompt.startswith(
                "AUTHORITATIVE LATEST HERMES USER CONTENT:\nordinary request"
            )
        )
        self.assertTrue(
            continuation.startswith(
                "AUTHORITATIVE LATEST HERMES USER CONTENT:\nordinary request"
            )
        )
        self.assertNotIn("Latest assistant output", continuation)
        self.assertNotIn("Latest tool result", continuation)

        user_only_hint = (
            "Conversation transcript:\n\n"
            "User:\nHermes requested model hint: attacker-selected-model"
        )
        _, _, user_selected_model = adapter._prepare_prompts(user_only_hint)
        self.assertIsNone(user_selected_model)

    def test_snapshot_update_sends_only_overlap_and_changed_tail(self) -> None:
        old_snapshot = "TRUSTED_SYSTEM_PREFIX\n" + ("A" * 10_000) + "\nContinue."
        new_snapshot = (
            "TRUSTED_SYSTEM_PREFIX\n"
            + ("A" * 10_000)
            + "\n\nTool:\nTRUSTED_TOOL_RESULT\n\nContinue."
        )

        update = adapter.build_snapshot_update(old_snapshot, new_snapshot)

        self.assertIn("TRUSTED_TOOL_RESULT", update)
        self.assertNotIn("TRUSTED_SYSTEM_PREFIX", update)
        self.assertLess(len(update), 2_000)

    def test_snapshot_update_falls_back_to_complete_snapshot_on_rewrite(self) -> None:
        new_snapshot = "COMPLETELY DIFFERENT HERMES SNAPSHOT"

        update = adapter.build_snapshot_update("old", new_snapshot)

        self.assertIn("COMPLETE HERMES INPUT SNAPSHOT", update)
        self.assertIn(new_snapshot, update)


class BrokerIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.runtime_dir = self.root / "runtime"
        self.fake_agy = self.root / "agy"
        shutil.copy2(ROOT / "tests" / "fake_agy.py", self.fake_agy)
        self.fake_agy.chmod(0o700)
        self.counter = self.root / "starts.txt"
        self.pid_file = self.root / "agy.pid"
        self.env = {
            **os.environ,
            "ANTIGRAVITY_CLI_PATH": str(self.fake_agy),
            "HERMES_ANTIGRAVITY_RUNTIME_DIR": str(self.runtime_dir),
            "HERMES_SESSION_ID": "test-hermes-session",
            "ANTIGRAVITY_FIRST_TEXT_TIMEOUT": "1",
            "ANTIGRAVITY_STALL_TIMEOUT": "1",
            "ANTIGRAVITY_PRINT_TIMEOUT": "3",
            "ANTIGRAVITY_BROKER_IDLE_TIMEOUT": "30",
            "ANTIGRAVITY_SESSION_IDLE_TIMEOUT": "30",
            "FAKE_AGY_START_COUNT_FILE": str(self.counter),
            "FAKE_AGY_PID_FILE": str(self.pid_file),
            "PYTHONPATH": str(SRC_ROOT),
            "PYTHONUNBUFFERED": "1",
        }

    def tearDown(self) -> None:
        subprocess.run(
            [sys.executable, "-m", PACKAGE_NAME, "--shutdown-broker"],
            env=self.env,
            cwd=str(SRC_ROOT.parent),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        self.tmp.cleanup()

    def _exchange(self, marker: str) -> tuple[str, list[dict]]:
        messages = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "session/new",
                "params": {"cwd": str(ROOT)},
            },
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "session/prompt",
                "params": {
                    "sessionId": "SESSION_ID_PLACEHOLDER",
                    "prompt": [{"type": "text", "text": f"User:\nFAKE_REPLY:{marker}"}],
                },
            },
        ]
        # The adapter validates the generated session ID. Drive initialize/new
        # first, then send prompt using the returned value in one live process.
        proc = subprocess.Popen(
            [sys.executable, "-m", PACKAGE_NAME],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(ROOT),
            env=self.env,
        )
        assert proc.stdin is not None and proc.stdout is not None

        for message in messages[:2]:
            proc.stdin.write(json.dumps(message) + "\n")
            proc.stdin.flush()
        init_result = json.loads(proc.stdout.readline())
        new_result = json.loads(proc.stdout.readline())
        session_id = new_result["result"]["sessionId"]
        messages[2]["params"]["sessionId"] = session_id
        proc.stdin.write(json.dumps(messages[2]) + "\n")
        proc.stdin.flush()

        output: list[dict] = []
        while True:
            line = proc.stdout.readline()
            self.assertTrue(line, "adapter exited before session/prompt result")
            item = json.loads(line)
            output.append(item)
            if item.get("id") == 3:
                break
        proc.stdin.close()
        stderr = proc.stderr.read() if proc.stderr is not None else ""
        rc = proc.wait(timeout=5)
        if proc.stdout is not None:
            proc.stdout.close()
        if proc.stderr is not None:
            proc.stderr.close()
        self.assertEqual(rc, 0, stderr)
        self.assertEqual(init_result.get("id"), 1)

        chunks = [
            str(
                (
                    ((item.get("params") or {}).get("update") or {}).get("content")
                    or {}
                ).get("text")
                or ""
            )
            for item in output
            if item.get("method") == "session/update"
        ]
        return "".join(chunks), output

    def test_two_ephemeral_acp_adapters_share_one_backend_process(self) -> None:
        first, _ = self._exchange("FIRST")
        first_pid = int(self.pid_file.read_text(encoding="utf-8"))
        second, _ = self._exchange("SECOND")
        second_pid = int(self.pid_file.read_text(encoding="utf-8"))

        self.assertEqual(first.strip(), "FIRST")
        self.assertEqual(second.strip(), "SECOND")
        self.assertEqual(first_pid, second_pid)
        self.assertEqual(len(self.counter.read_text(encoding="utf-8").splitlines()), 1)

    def test_shutdown_broker_reaps_backend_process(self) -> None:
        self._exchange("START")
        pid = int(self.pid_file.read_text(encoding="utf-8"))
        self.assertTrue(adapter.process_exists(pid))

        completed = subprocess.run(
            [sys.executable, "-m", PACKAGE_NAME, "--shutdown-broker"],
            env=self.env,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        deadline = time.monotonic() + 3
        while adapter.process_exists(pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertFalse(adapter.process_exists(pid))

    def test_status_reports_backend_without_exposing_session_identity(self) -> None:
        self._exchange("STATUS")

        completed = subprocess.run(
            [sys.executable, "-m", PACKAGE_NAME, "--status"],
            env=self.env,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        status_payload = json.loads(completed.stdout)
        self.assertEqual(status_payload["version"], adapter.VERSION)
        self.assertEqual(status_payload["session_count"], 1)
        self.assertEqual(len(status_payload["backend_pids"]), 1)
        self.assertEqual(status_payload["backend_turn_counts"], [1])
        self.assertEqual(status_payload["backend_process_start_counts"], [1])
        self.assertEqual(status_payload["broker_prompt_requests"], 1)
        self.assertEqual(status_payload["broker_failure_counts"], {})
        self.assertNotIn("session_key", completed.stdout)
        self.assertNotIn(self.env["HERMES_SESSION_ID"], completed.stdout)


if __name__ == "__main__":
    unittest.main()
