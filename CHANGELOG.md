# Changelog

All notable changes to this project are recorded here.

## 2.1.3 - 2026-09-15

### Changed

- `scripts/publish_to_pypi.py` accepts `--target pypi|testpypi` (default `pypi`) and now documents the TestPyPI trusted publisher URL in its DONE message. Use `--target testpypi` to verify a TestPyPI trusted publisher registration.
- `MAINTAINERS.md` and `CONTRIBUTING.md` updated to spell out the exact values for both the PyPI and TestPyPI trusted publisher registrations and to note that TestPyPI is a dry-run surface (`continue-on-error: true`).
- `CONTRIBUTING.md` mentions that `release.yml` signs PyPI digital attestations on every upload.

### Preserved

- No behavior change to the broker, the persistent `agy` lifecycle, or the live OAuth path.
- 21/21 offline tests still pass. Live OAuth smoke 9/9 still passes.
- No Hermes source change. No credential file read or written.

## 2.1.2 - 2026-09-15

### Added

- `install.py` launcher now discovers a usable Python in three places:
  - `HERMES_ANTIGRAVITY_PYTHON` environment override (highest priority),
  - `sys.executable` of the running launcher, if it can already import the package,
  - every `python3` / `python` on `PATH` and three well-known per-user locations (`~/.local/bin/python3`, `~/.local/share/hermes-antigravity-acp-venv/bin/python`, the same with `python3` suffix).
- New unit test `test_launcher_python_discovery_prefers_hermes_antigravity_python_override` locks in the discovery contract.

### Changed

- `.github/workflows/release.yml`: `publish-testpypi` job is now `continue-on-error: true`. TestPyPI is a dry-run surface; its unavailability must not flip the workflow conclusion from success to failure.

### Preserved

- No behavior change to the broker, the persistent `agy` lifecycle, or the live OAuth path.
- 20/20 offline tests still pass. Live OAuth smoke 9/9 still passes.
- No Hermes source change. No credential file read or written.

## 2.1.1 - 2026-09-15

### Changed

- Source layout: moved the single-file adapter to a real Python package at `src/hermes_antigravity_acp/`. This unblocks PyPI publication and keeps the CLI surface, broker lifecycle and offline tests unchanged.
- `install.py` now writes a small launcher that delegates to `python -m hermes_antigravity_acp`, so the installed adapter works with every supported Python and no longer embeds the full adapter body.
- `scripts/smoke_test.py` invokes the adapter via `python -m hermes_antigravity_acp` by default; the legacy `--adapter <path>` override is preserved for offline debugging.
- GitHub Actions now builds and publishes to PyPI via Trusted Publishing on every `v*.*.*` tag (no API token required).

### Added

- `pyproject.toml` (PEP 621 metadata, hatchling backend, console script `hermes-antigravity-acp`).
- Release workflow `.github/workflows/release.yml` that builds sdist + wheel and publishes to PyPI through `pypa/gh-action-pypi-publish` using GitHub OIDC.

### Preserved

- The `HERMES_COPILOT_ACP_COMMAND=...` binding keeps working unchanged.
- All 20 offline tests still pass and 9/9 live OAuth smoke checks still pass.
- No Hermes source change. No credential file read or written.

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
