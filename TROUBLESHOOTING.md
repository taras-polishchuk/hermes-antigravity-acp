# Troubleshooting

## Fast triage

```bash
agy --version
$HOME/.hermes/scripts/hermes-antigravity-acp --version
$HOME/.hermes/scripts/hermes-antigravity-acp --status
python3 install.py --check
PYTHONWARNINGS=error::ResourceWarning python3 -m unittest discover -s tests -v
```

Restart only the adapter broker:

```bash
$HOME/.hermes/scripts/hermes-antigravity-acp --shutdown-broker
```

The next Hermes request starts a clean broker automatically.

## Known failure signatures

### Adapter returns no output and `agy` exits successfully

Likely cause: `--print=` was combined with `--input-format stream-json`.

The equals form changes argument interpretation and can make the stream-json path a silent no-op.

Fix: use the shipped `build_agy_command()` result. Do not add `--print=`.

### Tool-oriented prompt hangs indefinitely

Likely cause: `--mode plan` or another permission-review mode is active. When Gemini selects an Antigravity-native tool, no interactive reviewer exists.

Fix: remove `--mode plan`, keep `--dangerously-skip-permissions`, and review `SECURITY.md`.

### `agy` works interactively but stalls from Hermes or a temp directory

Likely cause: launch-directory/project mapping mismatch.

The adapter deliberately starts `agy` from the user home rather than inheriting an arbitrary Hermes or temp CWD.

Fix: do not replace the broker's stable CWD with `os.getcwd()`.

### PTY version stalls or shows rich terminal output

Cause: `agy` detects a TTY and selects interactive behavior.

Fix: use stdin/stdout pipes. Do not use `pty.openpty()`.

### Every Hermes tool iteration is still cold

Checks:

1. Run adapter `--status` during the Hermes session.
2. Confirm `session_count` is non-zero.
3. Confirm the backend PID stays the same across tool iterations.
4. Compare `backend_turn_counts` with `backend_process_start_counts`.
5. Confirm `broker_failure_counts` is empty.
6. Confirm Hermes propagates `HERMES_SESSION_ID` to the external provider process.

If no stable session identity exists, the adapter intentionally falls back to ephemeral mode.

### Broker is not running

`--status` returns exit 1 and `broker: not_running` when no broker exists. This is normal before the first request or after idle expiry.

If a request cannot start it:

1. verify the runtime parent directory is writable;
2. verify no non-socket file occupies the broker socket path;
3. set an isolated `HERMES_ANTIGRAVITY_RUNTIME_DIR` and retry;
4. run the offline tests.

The adapter refuses to delete a non-socket path for safety.

### First text timeout

Default: 15 seconds.

Possible causes:

- expired OAuth login;
- provider/network latency;
- quota or entitlement issue;
- model identifier unavailable;
- Antigravity process startup regression.

Run an isolated probe:

```bash
python3 scripts/smoke_test.py --max-cold-seconds 30
```

Increasing the deadline is diagnostic, not proof that the latency requirement is met.

Tool-result continuations use `ANTIGRAVITY_CONTINUATION_FIRST_TEXT_TIMEOUT` instead. Keeping that deadline higher than the short-prompt deadline avoids converting one slow continuation into multiple cold Hermes retries.

### Stream/result mismatch

The adapter received `text_delta` chunks that do not equal the final Antigravity response. It terminates the backend rather than duplicate or corrupt output.

Recovery:

1. stop the broker;
2. reproduce with the smoke test;
3. record `agy --version`;
4. inspect Antigravity release notes;
5. update the event parser only after capturing the new event shape.

Do not concatenate both stream and result blindly.

### 301 or 302 appears

This project does not emit HTTP status codes. The symptom was not reproduced during development.

Required evidence before attribution:

1. exact command;
2. complete stderr;
3. response body;
4. whether the source was Hermes, `agy`, an OAuth endpoint, or another wrapper.

Do not infer that a printed number is an HTTP redirect code without the response context.

### OAuth expired

Run `agy` interactively and complete sign-in again. Do not paste or copy OAuth values into:

- Hermes config;
- shell history;
- issue reports;
- mission files;
- chat transcripts;
- this repository.

## Tool-flow debugging

Hermes expects either normal text or `<tool_call>` JSON blocks in OpenAI function-call shape.

If Gemini writes a prose tool request instead:

1. verify Hermes included the tool schema in the prompt;
2. verify the adapter directive is present in the first backend turn;
3. verify the same backend PID is reused for the tool result continuation;
4. capture only the generated tool-call text, never secrets or unrelated prompt content;
5. run Hermes with its supported verbose mode if available in the installed version.

If Antigravity executes a native tool instead of returning a block, see the residual security limitation in `SECURITY.md`.

## Upgrade recovery

The installer creates timestamped backups beside the active adapter. To roll back:

1. stop the broker;
2. copy the selected backup over the installed adapter;
3. restore mode `0700`;
4. run the adapter `--version` or a smoke test.

Do not delete backups until the live Hermes tool-flow test passes.
