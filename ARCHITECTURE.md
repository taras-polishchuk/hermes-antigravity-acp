# Architecture

## 1. Objective

Expose Antigravity's Google OAuth-backed Gemini access as an alternate Hermes model backend while preserving these boundaries:

1. Hermes remains the conversation and tool orchestrator.
2. Antigravity remains the OAuth owner.
3. The adapter never reads credential files.
4. No Hermes source modification is required.
5. A Hermes tool loop reuses model-side process state instead of cold-starting `agy` on every model call.

## 2. Runtime topology

```text
Hermes Agent
  |
  | ACP JSON-RPC over stdin/stdout
  v
Short-lived adapter frontend
  |
  | one request over a mode-0600 Unix socket
  v
Per-user broker
  |
  | serialized NDJSON stream-json
  v
One persistent agy process per HERMES_SESSION_ID
  |
  v
Google OAuth-backed Gemini service
```

The frontend and broker are two modes of the same Python file.

## 3. Why process-local persistence is insufficient

Hermes's `CopilotACPClient._run_prompt()` performs this sequence for every model call:

1. spawn the configured ACP command;
2. send `initialize`;
3. send `session/new`;
4. send one `session/prompt`;
5. collect `session/update` chunks;
6. close the ACP process.

A tool flow performs another model call after Hermes executes the tool. The original ACP process no longer exists. Therefore, an `agy` process owned directly by that frontend cannot be reused.

The broker outlives those frontends and uses the stable Hermes session identity already propagated through the subprocess environment.

## 4. Contracts

### 4.1 Hermes to frontend

The frontend implements the minimal ACP surface Hermes needs:

- `initialize`
- `session/new`
- `session/prompt`
- `session/cancel`

It advertises `agentCapabilities: {}`. Hermes tools are represented in prompt text, not exposed as ACP-native tool capabilities.

### 4.2 Frontend to broker

One newline-delimited JSON request per Unix-socket connection:

- `ping`
- `status`
- `prompt`
- `cancel`
- `shutdown`

A prompt response contains zero or more `chunk` events followed by exactly one `done` or `error` event.

The socket directory is mode `0700`; the socket and startup lock are mode `0600`.

### 4.3 Broker to Antigravity

The broker starts `agy` with:

```text
--input-format stream-json
--output-format stream-json
--disable-slash-commands
--dangerously-skip-permissions
[--model MODEL]
```

Known-bad flags are deliberately absent:

- no `--print=`;
- no `--mode plan`;
- no PTY.

Each model turn is one NDJSON `user` event. A live `agy` process accepts multiple such lines and runs one turn per line. `--conversation` is not required while the process remains alive.

If a previously successful child exits naturally, the broker retains its conversation ID and starts the replacement with `--conversation ID`. A timeout or protocol failure resets the conversation instead, because the remote state of an interrupted turn is ambiguous.

## 5. Prompt strategy

### First backend turn

The broker forwards:

- a complete Hermes input snapshot, including system instructions, transcript, and tool schemas;
- the adapter directive.

### Later backend turns

The broker forwards:

- the authoritative latest user content at the front;
- a byte-level tail update computed from the previous and current complete Hermes snapshots;
- 512 characters of overlap before the first changed byte;
- the adapter directive.

The adapter deliberately does not extract `Assistant:` or `Tool:` sections with regular expressions. The flattened ACP prompt has no escaping that can distinguish a real message boundary from role-like text inside user content. A byte-level longest-common-prefix comparison preserves only the changed transcript tail without assigning it a higher-trust role.

If the snapshots share fewer than 2,048 leading characters, the adapter treats the change as a rewrite and sends the complete current snapshot. Snapshot state stays in broker memory and is cleared after an unsafe timeout or protocol failure.

Only the latest user content is duplicated at the front so a large initial snapshot cannot truncate the actual task. Even if user content includes role-like labels, it remains user content; it is never promoted as assistant or tool state.

The model hint is parsed only from the trusted prelude before `Conversation transcript:`. A marker inside user content cannot select the child model.

## 6. Streaming and result integrity

Antigravity emits `step_update` events. The adapter forwards only `agent_response.text_delta` as ACP `agent_message_chunk` updates.

The final `result.response` is compared with the concatenated stream:

- no stream: emit the final response once;
- result begins with stream: emit only the missing suffix;
- mismatch: terminate the backend and return an error rather than deliver corrupt or duplicated text.

The frontend does not inspect or rewrite `<tool_call>` blocks.

## 7. Session lifecycle

### Stable mode

When `HERMES_SESSION_ID` exists:

- broker key: opaque Hermes session identity;
- backend lifetime: across short-lived ACP frontend processes;
- concurrency: serialized by one lock per backend;
- natural child exit: restart with the saved Antigravity conversation ID;
- unsafe failure: reset conversation and rebuild from the current Hermes transcript;
- cleanup: cancellation, timeout, disconnect, idle expiry, broker shutdown.

### Ephemeral fallback

When `HERMES_SESSION_ID` is absent:

- broker key: generated ACP session ID;
- backend lifetime: current ACP frontend only;
- cleanup: frontend EOF cancels the backend.

This fails safe: no accidental cross-conversation sharing.

## 8. Timeout state machine

```text
START
  -> waiting-for-first-text
       -> first-text timeout: terminate
       -> first text: streaming
  -> streaming
       -> stall timeout: terminate
       -> result: validate and return
  -> any state
       -> total timeout: terminate
       -> process exit/EOF: terminate and error
       -> client disconnect: terminate that session
```

The child is started in its own POSIX process group. Cleanup sends SIGTERM, waits, then escalates to SIGKILL.

## 9. Broker lifecycle and upgrades

The first frontend acquires a startup file lock, checks broker version/protocol, and starts the broker if needed. Concurrent frontend starts cannot create duplicate brokers.

An installer asks the old adapter to stop its broker before replacing the file. A future frontend refuses to treat a broker with a different version or protocol as healthy.

The broker exits automatically when:

- all sessions have expired; and
- the broker idle deadline passes.

## 10. Security boundaries

- OAuth files: Antigravity only.
- Prompts/responses: held in process memory; not logged by the adapter.
- IPC: local Unix socket restricted to the current OS user.
- Session identity: used as an opaque key and omitted from status output.
- Hermes tools: parsed and executed by Hermes safety controls.
- Antigravity native tools: textually prohibited, but not technically disabled by the available CLI interface. See `SECURITY.md`.

## 11. Rejected alternatives

### One persistent process inside the ACP frontend

Rejected because Hermes closes the frontend after every model call.

### Start a fresh `agy --conversation ID` process per model call

Rejected as the primary path because it preserves conversation storage but still pays process/bootstrap overhead and requires durable correlation between Hermes sessions and Antigravity conversation IDs.

It is used only when a previously successful persistent child exits naturally. The broker already owns the Hermes-to-Antigravity correlation in memory, so no prompt-derived identity or disk mapping is required.

### PTY

Rejected because `agy` changes to interactive/rich behavior and stalls under automation.

### Plan mode

Rejected because native tool attempts enter `request-review` without a reviewer.

### Modify Hermes source

Rejected by scope. The existing external-process provider contract is sufficient when paired with a broker.

## 12. Residual risks

1. Antigravity's stream-json event schema is not a versioned contract controlled by this project.
2. A model may invoke native Antigravity tools despite the directive.
3. Broker state is in-memory; a broker crash loses live process reuse but not Hermes conversation history.
4. The current Hermes shim buffers ACP chunks before exposing the completion to its outer streaming layer.
5. Provider latency and OAuth service availability remain external.
