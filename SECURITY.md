# Security

## Threat model

This adapter connects three trust domains:

1. Hermes, which owns conversation state and tool safety policy.
2. A local adapter/broker, which transports prompts and model output.
3. Antigravity, which owns Google OAuth state and can expose native agent tools.

The primary goals are credential isolation, local IPC isolation, bounded process lifetime, and preservation of Hermes's tool boundary.

## Credential boundary

The adapter does not:

- open Antigravity OAuth files;
- copy tokens into Hermes config;
- accept tokens over ACP or broker JSON;
- log environment variables;
- log prompts or responses;
- package user-specific credential state.

Antigravity discovers and refreshes its own OAuth session. File ownership and permissions remain Antigravity's responsibility.

## Local IPC

The broker uses a per-user Unix-socket directory:

- directory mode: `0700`;
- socket mode: `0600`;
- startup lock mode: `0600`.

The adapter refuses to replace a non-socket object at the expected socket path. Broker status omits session keys, conversation IDs, prompts, and response text.

Any process running as the same OS user can still connect to a user-owned Unix socket. The design does not defend against a fully compromised user account.

## Process containment

Each `agy` child runs in a separate POSIX process group. The adapter terminates that group on:

- first-text timeout;
- mid-stream stall timeout;
- total timeout;
- malformed result or stream/result mismatch;
- ACP client disconnect while streaming;
- explicit session cancellation;
- session idle expiry;
- broker shutdown.

Termination escalates from SIGTERM to SIGKILL after a bounded wait.

## The permission flag trade-off

The verified non-interactive path requires:

```text
--dangerously-skip-permissions
```

Without it, `--mode plan` enters `request-review` when Gemini selects an Antigravity-native tool, but no reviewer exists in the headless bridge. The result is an indefinite wait.

The adapter tells Gemini not to invoke Antigravity-native tools and to emit Hermes `<tool_call>` blocks instead. This is a prompt-level control, not a technical sandbox. A model can ignore it.

Consequences:

- do not treat this adapter as a hard security boundary against Antigravity-native tool execution;
- run it only under an OS account and workspace whose access you accept;
- do not expose the broker socket over a network;
- do not use the adapter for untrusted prompts without additional containment;
- review Antigravity's sandbox behavior before adding `--sandbox`; this project does not claim that the flag disables every native tool.

A future Antigravity protocol that supports a headless permission-deny response or a no-tools mode would allow this limitation to be closed properly.

## Hermes tool boundary

The intended flow is:

1. Gemini emits an OpenAI-shaped `<tool_call>` text block.
2. The adapter preserves it.
3. Hermes parses it.
4. Hermes runs the tool through its own safety checks.
5. The tool result returns to the same persistent model conversation.

The adapter does not execute Hermes tool JSON itself.

## Session isolation

Stable broker sessions are keyed by `HERMES_SESSION_ID`, treated as opaque data. The key is not printed by `--status`.

If Hermes does not provide a session ID, the adapter generates an ephemeral key and closes the backend at frontend EOF. It does not guess identity from prompt text, user text, CWD, or conversation similarity.

This avoids accidental sharing between independent chats that begin with similar prompts.

## Flattened prompt boundary

Hermes's generic ACP client sends a flattened text transcript. Role labels inside that text are not length-delimited or escaped, so user content can contain strings that look exactly like `Assistant:` or `Tool:` boundaries.

The adapter treats the complete prompt as an opaque snapshot. It does not promote regex-extracted assistant or tool sections into higher-trust headers. Continuations are computed by byte-level prefix comparison, not role parsing. The latest user content may be duplicated as user content at the front so the task survives model-context truncation. The requested model hint is accepted only from the pre-transcript Hermes prelude.

## Publication checklist

Before publishing a fork or release:

1. run the offline test suite;
2. scan tracked text for token-shaped values, OAuth fields, private keys, cookies, and operator-specific secrets;
3. confirm no credential, log, runtime socket, database, or generated conversation file is tracked;
4. confirm examples use `$HOME` or generic paths rather than a private workstation path;
5. inspect `git diff --cached` before commit;
6. do not publish live smoke output if it includes prompt or account metadata.

The repository `.gitignore` excludes Python caches and common local runtime artifacts, but ignore rules are not a substitute for reviewing the staged diff.

## Reporting vulnerabilities

Do not include tokens, OAuth responses, browser authorization URLs, cookies, raw prompt dumps, or Antigravity conversation databases in a public issue. Report a minimal reproduction with versions, event names, sanitized error text, and timing.
