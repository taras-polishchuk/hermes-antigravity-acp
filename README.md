# Hermes Antigravity ACP

Use the Google OAuth-backed [Antigravity CLI](https://antigravity.google/docs/cli/reference) (`agy`) as an alternate model backend for [Hermes Agent](https://hermes-agent.nousresearch.com) through Hermes's existing `copilot-acp` transport.

The adapter does not modify Hermes, does not copy OAuth credentials, and does not change the configured default provider. It adds a local broker so Hermes's short-lived ACP subprocesses can reuse one live `agy` process per Hermes session.

If `agy` exits naturally between successful turns, the broker restarts it with the saved `--conversation` ID instead of silently starting unrelated model state.

## Status

- Adapter version: 2.1.3
- Verified with Hermes 0.19.x and Antigravity CLI 1.2.2
- Platforms: Linux, macOS, WSL
- Python: 3.10+
- Transport: ACP JSON-RPC over stdin/stdout plus a private local Unix socket
- Authentication: owned entirely by Antigravity

This is a compatibility adapter, not a first-class `gemini-oauth` provider in Hermes.

## Why the broker exists

Hermes's `copilot-acp` client starts and closes the configured ACP command for every model call. A Hermes tool loop therefore creates multiple adapter processes. Keeping `agy` alive only inside one adapter process does not survive the next tool iteration.

The broker solves the real lifecycle mismatch:

```text
Hermes model call 1 -> short ACP adapter -> local broker -> persistent agy
Hermes model call 2 -> short ACP adapter -> local broker -> same agy
```

Hermes supplies `HERMES_SESSION_ID` to subprocesses. The broker uses it as an opaque local key. If the variable is unavailable, the adapter uses an ephemeral backend and closes it on ACP EOF.

## Requirements

1. Hermes Agent with the `copilot-acp` provider.
2. `agy` installed and available on PATH, or `ANTIGRAVITY_CLI_PATH` set.
3. A completed Antigravity Google OAuth login.
4. A POSIX platform with Unix sockets and `fcntl`.

Do not copy OAuth files into this repository or Hermes configuration.

## Install

### From PyPI (recommended for end users)

```bash
python3 -m pip install --user hermes-antigravity-acp
python3 -m hermes_antigravity_acp --version
```

If the system Python is externally managed, use a virtual environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install hermes-antigravity-acp
.venv/bin/hermes-antigravity-acp --version
```

Then point Hermes at the installed adapter:

```bash
export HERMES_COPILOT_ACP_COMMAND="$(command -v hermes-antigravity-acp)"
```

Or run the bundled installer after installing the package:

```bash
python3 -m pip install --user hermes-antigravity-acp
python3 -m hermes_antigravity_acp --version
python3 "$(python3 -c 'import importlib.util, sys, pathlib; print(next(pathlib.Path(p).parent for p in importlib.util.find_spec("hermes_antigravity_acp").submodule_search_locations)))"/install.py --configure-hermes
```

The last step resolves the installed `install.py` from the package's
distribution metadata and runs it with `--configure-hermes` to wire
Hermes automatically. Most users do not need this — exporting
`HERMES_COPILOT_ACP_COMMAND` to the absolute path of the installed
`hermes-antigravity-acp` binary is enough.

### From a Git checkout (for contributors)

```bash
git clone https://github.com/taras-polishchuk/hermes-antigravity-acp.git
cd hermes-antigravity-acp
PYTHONWARNINGS=error::ResourceWarning python3 -m unittest discover -s tests -v
python3 install.py
```

The installer:

- stops an older broker if the installed adapter supports it;
- backs up an existing adapter;
- performs an atomic replacement;
- installs mode `0700`;
- verifies SHA-256 and mode after installation;
- restores the previous destination automatically if verification fails.

Check for drift later:

```bash
python3 install.py --check
```

Point Hermes at the installed adapter using the non-secret environment binding:

```bash
export HERMES_COPILOT_ACP_COMMAND="$HOME/.hermes/scripts/hermes-antigravity-acp"
```

No API key is added to Hermes. Keep your existing default provider and select Gemini only when needed:

```bash
hermes chat \
  --provider copilot-acp \
  --model gemini-3.1-pro-high \
  -q "Reply with exactly HERMES_GEMINI_OK"
```

Hermes documentation for provider configuration is at <https://hermes-agent.nousresearch.com/docs/user-guide/configuration>.

## OAuth login

Run `agy` interactively and complete its Google sign-in flow. Antigravity owns refresh and storage. The adapter invokes `agy`; it never parses the credential store.

## Verify

Run the offline test suite:

```bash
PYTHONWARNINGS=error::ResourceWarning \
  python3 -m unittest discover -s tests -v
```

Install the adapter and persist the non-secret `HERMES_COPILOT_ACP_COMMAND` binding in the active Hermes profile:

```bash
python3 install.py --configure-hermes
```

To point Hermes at an adapter that lives somewhere else without touching the active profile, export the variable manually:

```bash
export HERMES_COPILOT_ACP_COMMAND="$HOME/.hermes/scripts/hermes-antigravity-acp"
```

Run an isolated two-turn OAuth smoke test:

```bash
python3 scripts/smoke_test.py
```

The smoke test passes only when:

- both exact markers are returned;
- both ACP adapter invocations share one backend PID;
- cold and warm turns meet the configured latency limits;
- broker shutdown reaps the backend process.

Inspect or stop the default broker:

```bash
$HOME/.hermes/scripts/hermes-antigravity-acp --status
$HOME/.hermes/scripts/hermes-antigravity-acp --shutdown-broker
```

`--status` reports counts, PIDs, backend starts, completed turns, and failure classes only. It does not expose Hermes session IDs, conversation IDs, prompts, or tokens.

## Tool flow

Hermes sends tool schemas in the prompt. When Gemini needs a Hermes tool, the model must return an OpenAI-shaped block:

```xml
<tool_call>{"id":"call_1","type":"function","function":{"name":"read_file","arguments":"{\"path\":\"README.md\"}"}}</tool_call>
```

The adapter preserves the text exactly. Hermes parses the block, runs the tool through its own safety layer, and sends the tool result on the next model call. The broker then forwards a byte-level tail update of the current Hermes snapshot to the same `agy` process. It never promotes assistant- or tool-like text from user content into adapter-trusted state.

The adapter emits ACP message chunks as soon as Antigravity emits `text_delta`. The current Hermes `copilot-acp` shim still assembles those chunks before returning its OpenAI-compatible completion, so this improves timeout and protocol behavior but does not guarantee token-by-token terminal rendering.

## Timeouts and lifecycle

| Environment variable | Default | Purpose |
|---|---:|---|
| `ANTIGRAVITY_FIRST_TEXT_TIMEOUT` | 45s | Maximum wait for the first model text delta |
| `ANTIGRAVITY_CONTINUATION_FIRST_TEXT_TIMEOUT` | 45s | First-text deadline for tool-result and resumed turns; prevents retry amplification |
| `ANTIGRAVITY_STALL_TIMEOUT` | 120s | Maximum silence after streaming starts |
| `ANTIGRAVITY_PRINT_TIMEOUT` | 600s | Absolute turn deadline |
| `ANTIGRAVITY_SESSION_IDLE_TIMEOUT` | 900s | Close an idle per-Hermes-session backend |
| `ANTIGRAVITY_BROKER_IDLE_TIMEOUT` | 1800s | Exit the broker after all sessions are gone |
| `ANTIGRAVITY_BROKER_START_TIMEOUT` | 5s | Broker readiness deadline |
| `HERMES_ANTIGRAVITY_RUNTIME_DIR` | per-user temp runtime | Override socket/lock directory, mainly for tests |
| `ANTIGRAVITY_CLI_PATH` | discovered under the user home | Override the `agy` executable |

All timeouts are bounded. Timeout, protocol corruption, client disconnect, explicit cancellation, idle expiry, and broker shutdown terminate the affected process group.

## Reference performance

A local WSL validation on 2026-09-15 measured:

- direct persistent adapter cold turn: 9.70s;
- second turn on the same `agy` process: 4.94s;
- backend PID reused: yes;
- backend alive after broker shutdown: no.

End-to-end Hermes measurements include Hermes startup, context assembly, tool execution, and session persistence:

- cold exact-marker CLI request: 21.77s wall;
- one `read_file` tool loop with a roughly 54k-token first snapshot: 54.84s wall, 2 backend turns, 1 backend process, 0 broker failures.

The adapter meets the 15s target at the backend boundary. A fresh Hermes CLI process can exceed 15s because of Hermes startup/context overhead; this adapter does not modify that layer.

These numbers are evidence from one machine and account, not a provider SLA.

## Known limitations

1. `--dangerously-skip-permissions` is required to prevent Antigravity permission-review deadlocks. See `SECURITY.md` before use.
2. Native Windows is not supported by this release.
3. Broker reuse depends on Hermes exposing `HERMES_SESSION_ID`; otherwise the safe fallback is ephemeral.
4. A model can ignore the textual instruction not to use Antigravity-native tools. This adapter reduces that risk but cannot enforce it at the Antigravity protocol boundary.
5. HTTP-like 301/302 reports were not reproduced. Capture the exact stderr/body before attribution.

## Repository map

| Path | Purpose |
|---|---|
| `hermes_antigravity_acp.py` | Adapter, broker, persistent `agy` lifecycle |
| `install.py` | Backup-safe local installer and drift check |
| `scripts/smoke_test.py` | Isolated live OAuth and latency test |
| `tests/` | Offline unit and broker integration tests |
| `ARCHITECTURE.md` | Contracts, sequence, lifecycle, rejected alternatives |
| `TROUBLESHOOTING.md` | Known failure signatures and recovery |
| `SECURITY.md` | Credential and tool-execution boundaries |

## License

MIT. See `LICENSE`.
