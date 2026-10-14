# Selectable local Codex login OAuth transport

## Current status

`codex-oauth` is an **explicit, executable local provider selection**, not a hidden
readiness gate. `disabled-codex` remains the default; finding credentials or logging
in does not change it. No API key, SIWC substitution, custom endpoint, credential
copy, browser scraping, or hosted deployment is introduced.

The public `CodexOAuthProvider.answer()` performs:

`initialize → initialized → config/read → account/read → thread/start → turn/start → validated completion`.

Tests substitute only the subprocess executable with a labeled protocol fixture,
not a readiness function. Actual Discord `/ask` callbacks select the provider and
persist the generated candidate answer using the merged PR12 storage contract.
Restart, manual `/resolved`, confirmed-only retrieval, source deletion and privacy
purge remain covered. Generated answers are never automatically verified knowledge.

**Implemented transport is not a claim of authenticated live GPT success.** No
existing auth was accessed, no login was performed and no live turn was sent during
this work. Public hosted use and Discord deployment still need their own permission
and verification; the runtime does not manufacture a permanent technical denial.

## Login-ready local run

Use a dedicated OS account without unrelated private files for real operation.
A read-only sandbox is **not a host-read confidentiality boundary**. Keep the
application data directory private, outside a source checkout, and free of custom
Codex configuration, skills, MCP servers, plugins and hooks. Do not copy an existing
personal `auth.json`, point at Hermes credentials, or add an API key.

After separate authorization to log in and make a local live request:

```bash
# Activate the project's installed Python environment first.
APP_DATA="$HOME/.local/share/discord-helper"
# Installs the official pinned @openai/codex@0.162.1, not a global npm install.
discord-helper --data-dir "$APP_DATA" install-codex
# Operator completes the official device login. Browser variant: --browser.
discord-helper --data-dir "$APP_DATA" codex-login
# This is offline: creates/checks local DB/commands, does not inspect auth or spawn Codex.
discord-helper --data-dir "$APP_DATA" run --provider codex-oauth --check
# Only after Discord credentials/setup and the intended test guild are authorized:
discord-helper --data-dir "$APP_DATA" run --provider codex-oauth --sync-guild TEST_GUILD_ID
```

`TEST_GUILD_ID` is an operator-supplied numeric ID, not a literal command value.
The management command uses the same `<data>/codex` for official login and runtime.
Login uses private application HOME/cwd, file credential storage and ChatGPT-only
login. Runtime uses the platform-native executable from the application-local npm
install, avoiding a Node shim under its minimal PATH. An explicit absolute native
path can instead be supplied with `--codex-executable`; initialization verifies
**0.162.1** and the exact application `CODEX_HOME`. Missing binaries, invalid paths,
invalid configuration and signed-out/API-key accounts produce real failures.

The alternate module entry point accepts
`python -m helperbot --provider codex-oauth --data-dir /absolute/app/data
--codex-executable /absolute/native/codex` with the same factory. Its database path
is separately selected with `--database`. The installed systemd unit still starts
the disabled default: this change does not silently activate or deploy a service.

## Concrete restrictions (not a zero-tools promise)

The official package is pinned by `tools/protocol/package-lock.json`. Controls
were checked against the **rust-v0.162.1** source and the actual native binary.

- Every answer gets a new process/session, empty private request HOME and cwd, and
  an ephemeral thread with no session path. No resume/fork/thread sharing.
- Child environment is only HOME, CODEX_HOME, system-default PATH, LANG and TMPDIR.
  No Discord token, API key, parent cwd, proxy settings or unrelated auth variables.
- `sandbox_mode="read-only"` is explicit; turn `sandboxPolicy` is
  `{"type":"readOnly","networkAccess":false}`. This restricts tool writes and
  tool network access, **not** the official process's necessary model connection.
- `approval_policy="never"` prevents approval-based escalation; every server request
  is still denied, including approvals, dynamic tools, user input, external token
  refresh and unknown future methods. No bypass/full-access flags are used.
- **Important correction:** `untrusted` remains in the generated schema but the
  pinned binary rejects it as retired. The previous fixture-only setting would not
  have worked live. `never` + read-only is accepted by the real pinned binary.
- Disable shell tool, view-image, code-mode/code-mode-only, apps, plugins,
  multi-agent/v2, browser/computer use, image generation, shell snapshot, hooks,
  memories and permission-request tools through verified feature switches. Disable
  web search; no MCP servers; shell environment inheritance is `none`; login shells
  are disabled. Host skill discovery is skipped; project document byte budget is 0.
- `tools.update_plan.enabled=false` and experimental user-input utility are set,
  but these utility fields are omitted by public `config/read`; their setting is
  not represented as proof of an empty tool registry. Removed `js_repl` and
  `apply_patch_freeform` flags are deliberately not asserted as security controls.
- Before authentication/model work, read the resolved configuration and verify
  supported execution controls. Reject injected MCP/hooks/model-provider/config
  overrides; reject application `config.toml`. Startup warning text is discarded:
  a warning alone is not an inference ban. Actual invalid settings fail validation.
  Delayed notices also do not constitute an artificial gate; protocol errors,
  mismatched effective controls, tool items and server requests still abort.
- Check returned thread sandbox, approval policy, reviewer, cwd, model provider,
  ephemeral flag and absence of a session path before sending user data.
- Reject symlinked runtime/auth paths and non-private/non-owner auth files without
  reading their contents. Official Codex owns loading and refresh of app OAuth.

These controls **mitigate tool effects; they do not guarantee zero tools**. The
pinned tool plan can still register built-in utilities/apply-patch or model-specific
items independently of shell switches. Read-only can allow reads of files visible
to the OS account. Tool-event rejection is detection, not proof nothing executed
before an event arrived. The account and filesystem must be appropriately isolated;
an empty HOME/cwd does not hide all same-UID files. Unsupported OS/sandbox failures
are real runtime failures, never a reason to switch to dangerous bypass mode.

The app-server itself retains access needed for OAuth/model traffic and may write
internal state in CODEX_HOME. Ephemeral threads/history-none are not a promise of
zero local telemetry/cache files or remote provider retention. Same-UID malicious
filesystem races, escaped child sessions and host termination are not container
security guarantees. Hosted authorization remains separate from local selection.

## Protocol, privacy and cleanup

Only question, short history and supplied case id/question/solution are sent as
JSON data; instructions are separate. Discord identities and source metadata are
excluded. Inputs are bounded before IO. Frames are at most 64 KiB, total wire 1 MiB,
2048 events, 64 queued notifications, 32 assistant items, 8 KiB per item and 32 KiB
streamed deltas. Final JSON must contain only non-empty text (at most 1000 chars)
and at most three distinct integer IDs drawn from supplied evidence. Unknown IDs,
boolean IDs, extra fields, incomplete/failed turns and stream mismatches fail closed.
No partial text is published before terminal success and source/output validation.

All non-message/reasoning items and unsupported notifications are rejected. Errors
are sanitized; child stderr and server payloads are not logged. Each request has a
20-second default deadline. Completion, errors, timeout and cancellation kill the
owned POSIX process group and reap/drain its child, including cancellation during
spawn and repeated cancellation during cleanup. Privacy invalidation discards late
results and prevents persistence/revival; it cannot retract already-sent remote
requests, already-posted Discord data, backups or provider-side retention.

## Reproducible evidence, no credentials

```bash
npm ci --prefix tools/protocol --ignore-scripts --no-audit --no-fund
mkdir -p .runtime
python tests/probe_codex.py tools/protocol/node_modules .runtime
python tests/probe_codex_answer.py tools/protocol/node_modules .runtime
python -m pytest -q
```

The second probe calls **public `answer()` without patches** in a fresh temporary
app home. On macOS ARM64 it returned exactly `Codex managed ChatGPT login required`
after real initialize/config-read/account-read, cleaned request directories, and
created no auth file. Its executable was:

`tools/protocol/node_modules/@openai/codex-darwin-arm64/vendor/aarch64-apple-darwin/bin/codex`

This is real auth-needed behavior, not an artificial zero-tools denial. CI also
runs it on the official Linux binary alongside existing schema/handshake, full
Python test matrices and real systemd lifecycle/recovery jobs. Fixture model output
is explicitly synthetic. Real model completion/refresh/account entitlement still
requires a separately authorized app login and bounded live test; neither is
claimed here.

## Verified primary references

- Pinned configuration schema: https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/core/config.schema.json
- Runtime configuration validation (retired `untrusted`): https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/core/src/config/mod.rs
- Feature stages (including removed flags): https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/features/src/lib.rs
- Actual tool registration: https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/core/src/tools/spec_plan.rs
- Sandbox/permission resolution: https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/core/src/config/permissions.rs
- Public protocol schemas: https://github.com/openai/codex/tree/rust-v0.162.1/codex-rs/app-server-protocol/schema/json

The policy investigation in `CODEX_OAUTH_DECISION.md` is distinct from these runtime
controls. No policy restriction was bypassed or transformed into hosted approval.
