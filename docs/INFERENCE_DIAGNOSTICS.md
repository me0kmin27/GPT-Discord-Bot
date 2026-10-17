# Safe inference diagnostic (explicit opt-in)

The root `warning` notification fix is separate (PR #17). This command is an
operator diagnostic, not a claim of live readiness and not an authentication
replacement. It calls the installed **public `provider.answer`** with a fixed,
harmless synthetic question, empty history and empty evidence. It opens no Discord
connection or knowledge database. No API key is requested or used.

## Operator command

After installing this module in the same application environment:

```sh
~/.local/share/discord-helper-install/venv/bin/python -m helperbot.inference_probe --live
```

To diagnose an older installation without replacing it, copy the reviewed
`helperbot/inference_probe.py` file to an operator-selected location and run that
single file with the **installed application's interpreter**, for example:

```sh
~/.local/share/discord-helper-install/venv/bin/python "$HOME/inference_probe.py" --live --data-dir "${XDG_DATA_HOME:-$HOME/.local/share}/discord-helper"
```

Use the actual data directory if installation overrides it. No source checkout
or auth file copy is needed. Do not run using an unrelated/global interpreter.
Without `--live`, the command refuses before importing the provider or touching
application data. With `--live`, it authorizes one model request using the
operator's existing application-isolated Codex OAuth and may consume plan usage.
The official provider may refresh its own auth as usual. The probe itself does
not inspect credentials, invoke login, change configuration, or restart services.
It explicitly chooses `codex-oauth`; it does not check the running service's
provider selection or verify the Discord delivery path.

## Output and meaning

Only fixed stage/category/exception labels, bounded integer RPC code (when
available), duration in milliseconds, answer-success/length, and allowlisted
internal source filenames/line numbers are emitted. No absolute source paths,
exception bodies, locals, prompts, answers, auth/account fields, or logs.
`http_status` is currently null; no HTTP status is inferred from error text.
Old installed providers that discard numeric codes continue to report null.
Current phased providers use **preparation up to 60 seconds, then generation up to
240 seconds** by default, without a competing total-20-second probe timer. Older
installed providers retain their existing 20-second probe guard. See
[the shared timeout contract](timeout-contract.md). This standalone probe builds
a default provider; it does not load `runtime.json` model/search/budget overrides
and therefore does not reproduce the running service's exact configuration.

- `account/login_required`: managed ChatGPT account was not available in the
  selected application home; check that the operator used the same data directory.
- `config/config_rejected`, `thread/thread_rejected`: effective restriction
  validation failed; compare the pinned version/configuration, do not disable it.
- `protocol/notification_rejected`: the parser rejected a method/shape. Check the
  installed patch and version; do not paste raw protocol logs.
- `protocol/rpc_rejected`: RPC failure; use the numeric code if present.
- `completion/response_rejected`: terminal answer or JSON/citation contract did
  not pass; not an empty-knowledge gate.
- `preparation/deadline_exceeded` or `generation/deadline_exceeded`, origin `owned`:
  that application's phase budget expired. `elapsed_ms` is monotonic work-phase
  elapsed time and `deadline_ms` is its configured duration budget. Cleanup and
  delivery can add time afterward.
- `*/timeout`, origin `child_or_native`: a child/native timeout was observed, not
  proof that the application's budget expired. Known phase boundaries include
  their elapsed/budget values. Older uninstrumented providers report null timing
  and cannot distinguish ownership; do not interpret those as proven early native
  failures or proven deadline expiry.
- `answer/unknown`: unclassified failure; internal locations identify the catch
  boundary without revealing the exception body.

Exit 0 means the synthetic public provider request returned a valid nonempty
answer with empty citations. Exit 1 is a failed attempt; exit 2 means no opt-in or
invalid arguments; exit 130 is a sanitized interruption. Fixture successes are explicitly synthetic, not model output.
If the running bot still fails, supply only its fixed diagnostic category and the
probe JSON. The original bot fallback wording and a fresh no-match Discord request
remain important to distinguish inference from delivery/persistence failures.

## Investigation limits

Credential-free pinned native initialize/config/account/thread probes passed;
no authenticated model call was made by this worker. The parent separately
reported the live `warning` failure and differential success. Another schema
observation: pinned MessagePhase permits null, whereas the adapter requires
`final_answer`. A fixture reproduced that incompatibility, but it was **not** the
observed live cause; no phase fallback or response-validation relaxation is
included here. Treat it as a separate compatibility follow-up if observed.

## Tests

`tests/test_inference_diagnostics.py` exercises opt-in refusal, synthetic positive
and negative results, secret-bearing exceptions/stdout/stderr/logging, RPC numeric
code retention, fixed service categories, argument errors, missing installation,
empty-evidence citations, and legacy-provider 20-second deadline wiring. Existing
transport tests separately exercise actual subprocess timeout and cleanup.

Historical PR #18 combined local suite: **436 passed, 1 skipped** (macOS/Python 3.9).
A real standalone credential-free run against an archived `f1c0957` installation
and the pinned official native binary returned exit 1, stage `account`, category
`login_required`, answer_success false, answer_length 0, duration_ms 374, with
empty stderr and no auth file created. This verifies the backward-compatible
operator probe, not successful inference. No existing auth was accessed.

## Runtime drift / follow-up ownership

The parent/operator owns the separately authorized live warning hotfix,
`gpt-6.1-sol` / low effort override and subsequent web-search request. This PR
changes none of those settings and must not be deployed as a blind installed-file
replacement. Preserve/reconcile authorized overrides on upgrade. Persistent
operator configuration and explicitly opt-in `webSearch` item handling require a
separate bounded change; this diagnostic does not enable web search or permit
other tool items. Do not turn the existing tool allowlist into an allow-all list.
