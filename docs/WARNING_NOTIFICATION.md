# Codex `warning` notification regression

## Scope

The pinned official `@openai/codex` 0.162.1 native binary generates a
`ServerNotification` variant named `warning`, with `WarningNotification` fields:
required string `message`, optional string-or-null `threadId`.
The adapter previously rejected this valid method as unsupported, even after
successful authentication and thread creation. This is unrelated to whether
retrieval found matching knowledge.

The change validates this shape, discards the warning text, and retains a
non-null thread target for the existing completion scope check. A server request
(with `id`) is still rejected before this branch. Unknown notifications, tool
items, model/config/thread restrictions and output/citation validation remain
unchanged. Advisory warnings do not establish that those restrictions failed;
their effective-state checks remain authoritative.

## Evidence

- Generated schema from the project-installed native 0.162.1 binary, with fresh
  isolated HOME/CODEX_HOME and no existing auth. `WarningNotification.json` and
  `ServerNotification.json` confirm the shape above.
- Independent credential-free native config/thread probe: initialize passed;
  effective configuration passed; account was signed out; ephemeral thread
  creation returned readOnly/networkAccess=false, approvalPolicy=never,
  approvalsReviewer=user, modelProvider=openai and null thread path. No turn or
  authenticated inference was attempted by this worker.
- Regression RED: valid warning notifications caused `Codex unsupported
  notification` (4 failed, 3 passed). GREEN includes warning both before the
  turn/start RPC result and during completion, empty evidence and empty citations.
- Parent operator-session observation (not this worker's execution): original
  installed public provider.answer failed on method `warning` in 0.54 seconds;
  a process-local allowlist-only differential returned validated answer length 2
  in 6.14 seconds using the operator's existing OAuth. This was not a deployment
  and no auth/answer body is recorded here.
- Minimal fix checkout: `python -m pytest -q` -> **421 passed, 1 skipped** on
  local macOS/Python 3.9. The skip is the existing Linux-only check.

- Parent subsequently reported an operator-authorized installed-file hotfix:
  generic `warning` goes through the existing sanitized `configWarning` branch,
  with a pre-change backup and service restart. This is a live patch atop the
  prior installed revision, not deployment of this PR. This PR additionally
  validates the warning shape and preserves a non-null thread scope.
- CI now includes Python 3.13 to match the operator-reported interpreter.

## Public reference

Pinned schema:
https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/app-server-protocol/schema/json/v2/WarningNotification.json

## Remaining verification

Run final-head CI and operator-owned inference with the actual deployed patch.
Repository tests and the process-local differential are not proof that the
running Discord service has been updated. Do not merge or deploy implicitly.
