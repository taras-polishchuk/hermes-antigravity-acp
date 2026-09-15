"""Hermes Antigravity ACP — local ACP bridge for the Antigravity CLI.

This package contains the adapter and broker used by Hermes Agent's
``copilot-acp`` provider. Public surface:

- ``adapter`` — the long-lived broker and per-session ``agy`` lifecycle.
- ``__main__`` — CLI entry point. Run ``python -m hermes_antigravity_acp``
  or the ``hermes-antigravity-acp`` console script.
- Top-level names from ``adapter`` are re-exported here for the package
  surface (``VERSION``, timeouts, error classes, helpers, ``process_exists``,
  ``AgySession``, ``BrokerState``, etc.).
"""

from __future__ import annotations

from .adapter import *  # noqa: F401,F403 - intentional re-export
from .adapter import (
    BROKER_PROTOCOL_VERSION,
    DEFAULT_CONTINUATION_FIRST_TEXT_TIMEOUT,
    DEFAULT_FIRST_TEXT_TIMEOUT,
    AdapterTimeout,
    AgySession,
    BrokerState,
    ClientDisconnected,
    VERSION,
    build_agy_command,
    build_snapshot_update,
    process_exists,
    run_broker,
    shutdown_broker,
)

# Underscore-prefixed helpers are surfaced explicitly so tests and
# third-party extensions can introspect the broker protocol without
# importing the private ``adapter`` submodule directly.
from .adapter import (  # noqa: F401 - intentional re-export
    _broker_action,
    _broker_healthy,
    _handle,
    _handle_broker_client,
    _latest_user_content,
    _model_from_prompt,
    _prepare_prompts,
    _read_socket_lines,
    _request_broker,
    _runtime_dir,
    _send,
    _send_line,
    _socket_path,
    _start_broker,
    _terminate_process,
)

__all__ = [
    "BROKER_PROTOCOL_VERSION",
    "DEFAULT_CONTINUATION_FIRST_TEXT_TIMEOUT",
    "DEFAULT_FIRST_TEXT_TIMEOUT",
    "AdapterTimeout",
    "AgySession",
    "BrokerState",
    "ClientDisconnected",
    "VERSION",
    "build_agy_command",
    "build_snapshot_update",
    "process_exists",
    "run_broker",
    "shutdown_broker",
]
