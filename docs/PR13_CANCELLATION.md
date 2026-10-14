# PR13 cancellation follow-up

## Scope and root cause

Independent review of `b93ba96c56367e46664b0f1070b9598a8798e659` found that
Python 3.9's `asyncio.wait_for` can return a completed child's result after
caller cancellation was accepted, before the wrapper resumes. Both the public
Codex provider and Service used that wrapper. The real Service consequently
saved a generated answer after accepted cancellation. This was not a demonstrated
privacy-purge resurrection or process leak.

Python >=3.9 remains supported. No unconditional provider gate was added.
The provider remains explicitly selectable with disabled as the default.

## Correction

`helperbot/async_utils.py:wait_owned` uses `asyncio.wait` with a deadline, cancels
unfinished owned work, and shields only settlement. It consumes child exceptions
even when cancellation wins a completed-child race. Repeated cancellation waits
for settlement and propagates cancellation, including during timeout cleanup.
A child returning after cancellation cannot convert a genuine deadline into
success. Both `CodexOAuthProvider.answer` and `Service._ask` use the helper.

Subprocess spawn ownership, process-group kill, drain/reap and temporary-directory
cleanup remain in the existing transport. Storage is unchanged: cancellation now
escapes before generated-answer persistence; the question candidate created
before inference is not rolled back. Existing explicit privacy guards remain.
An uncooperative provider which never settles can still delay cleanup indefinitely;
Python cancellation is cooperative, not a general hard-kill guarantee.

## Deterministic RED -> GREEN (local Python 3.9.6)

- Read and executed both independent real-subprocess repro scripts without gate,
  parser or storage patches. Before correction, public answer returned success
  after `cancel() == True`; real Service saved one generated row.
- Added public-boundary tests before production changes. Both failed for the
  exact defect: `(propagated, generated_count)` was `(False, 0)` for provider and
  `(False, 1)` for Service, rather than `(True, 0)`.
- After correction both original repros report `CANCEL_PROPAGATED`, accepted
  cancellation true, request cleanup true; Service generated-row count is zero.
- Focused suite: **22 passed in 1.28s**. Covers completed-child cancellation at
  provider, Service and nested-provider boundaries; same-turn completion/error
  and cancellation in both orders; normal success/error/self-cancellation;
  genuine timeout with cancellation-suppressing child; repeated cancellation
  during timeout/cancellation settlement; actual fixture process cleanup and
  real SQLite no-late-save; successful persistence and cancel-after-done negative.
- Full suite: **381 passed, 1 skipped in 10.03s**. Skip is Linux-only local check.
  `compileall` and `git diff --check` passed.
- Fixture answers are explicitly synthetic, NOT live model responses. Instrumented
  spawn/reap gates observe real subprocesses; no authentication or provider gate
  is patched.

## Signed-out official binary

Actual macOS ARM64 pinned native binary, fresh application data directory, public
`answer()` returned upstream-account-driven `Codex managed ChatGPT login required`:
`public_answer=auth-needed`, `existing_auth_accessed=false`, `auth_created=false`,
`live_inference=false`, `request_cleanup=true`.

CI now includes supported Python 3.9 alongside 3.11 and 3.12, plus the existing
Linux native signed-out probes and disposable systemd checks. Exact final-head
CI/readback is recorded in the PR follow-up and external project evidence after
push; this file does not claim an unobserved future CI result.

No login, existing credential access, authenticated inference, deployment or merge
is authorized or performed here. Previous host filesystem/read-only/tool-effect
and hosted-permission limitations remain; this fixes cancellation, not those
separate runtime authorization boundaries. Independent review of the updated
exact head is still required before merge.
