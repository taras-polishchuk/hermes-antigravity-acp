# Changelog

All notable changes to this project are recorded here.

## 2.1.0 - 2026-09-15

### Added

- Default initial first-text timeout raised to 45 seconds to avoid retry amplification against Hermes sessions with large context windows.
- `install.py --configure-hermes` persists the non-secret `HERMES_COPILOT_ACP_COMMAND` binding into the active Hermes profile (resolved through `hermes config env-path`), preserving existing values and original file mode.
- Atomic, mode-preserving helper for writing only the `HERMES_COPILOT_ACP_COMMAND` binding.
- Default-version constant exposed as `adapter.DEFAULT_FIRST_TEXT_TIMEOUT` for offline verification.

### Preserved

- No `--print=` in stream-json mode.
- No PTY.
- No `--mode plan` permission-review deadlock.
- Stable Antigravity launch directory.
- Hermes-owned `<tool_call>` execution path.

## 2.0.0 - 2026-09-15

### Added

- Per-user Unix-socket broker keyed by Hermes session identity.
- One persistent `agy` stream-json process per active Hermes session.
- `--conversation` recovery when a previously successful child exits naturally.
- First-text, stall, total, session-idle, and broker-idle deadlines.
- Separate continuation first-text deadline to prevent retry amplification.
- Process-group cleanup on timeout, cancellation, disconnect, expiry, and shutdown.
- ACP chunk forwarding with stream/result integrity checks.
- Byte-level snapshot-tail continuations that avoid replaying roughly 50k tokens per tool iteration.
- Complete-snapshot fallback when the Hermes prompt is rewritten rather than extended.
- Latest-user duplication for task survival without assistant/tool role promotion.
- Model-hint parsing restricted to the trusted pre-transcript Hermes prelude.
- Immediate cancellation without waiting for the active model deadline.
- Process-group cleanup even when the child leader exits before descendants.
- Stale-broker socket handoff sequencing and detached-launcher cleanup.
- `--status`, including non-sensitive turn/start/failure counters, plus `--shutdown-broker` and `--version` operations.
- Rollback-safe installer with backup, atomic replacement, SHA-256 verification, and drift check.
- Automatic destination restoration when install verification fails.
- Offline unit/integration tests and isolated live OAuth smoke test.
- Architecture, security, and troubleshooting documentation.

### Preserved

- No `--print=` in stream-json mode.
- No PTY.
- No `--mode plan` permission-review deadlock.
- Stable Antigravity launch directory.
- Hermes-owned `<tool_call>` execution path.

## 1.0.0 - 2026-09-14

- Initial local ACP adapter.
- One fresh `agy` process per model call.
- Google OAuth remained managed by Antigravity.
