"""CLI entry point for the hermes-antigravity-acp package.

The dispatcher lives in :mod:`hermes_antigravity_acp.adapter` so the same
code can be invoked as ``hermes_antigravity_acp`` (script), as
``python -m hermes_antigravity_acp``, or through the
``--launch-broker``/``--broker``/``--shutdown-broker``/``--status``/
``--version`` subcommands.
"""

from __future__ import annotations

from .adapter import main as adapter_main

if __name__ == "__main__":
    raise SystemExit(adapter_main())

main = adapter_main
