# Persistent generated-answer candidates

## Implemented boundary (not live provider readiness)

`Service.ask` now attaches a validated generated answer to the explicitly submitted
question candidate **before returning success**. The answer stays unconfirmed: only
an authorized human's `/resolved case_id:… solution:…` writes the confirmed solution.
Neither search nor provider evidence/history reads the stored generated-answer table.
A human can retain, correct, or replace the generated advice in their explicit summary;
there is no automatic copying or promotion.

This closes the candidate question/answer **storage** gap noted by transport PR #11.
It does not remove its fixed zero-tools readiness gate or enable `DisabledCodex`.
No existing authentication was accessed, no login/live inference/API substitute or
Discord deployment was performed. All generated test answers are explicitly synthetic.

## SQLite migration and storage contract

- The original database is schema version `0` (SQLite `user_version`). Startup migrates
  additively to version `1` in a single `BEGIN IMMEDIATE` transaction. Existing channel,
  candidate, confirmed solution, source receipt, history, and sequence values are preserved.
  Reopening version 1 is idempotent; unknown versions fail closed without schema writes.
  Failed migration rolls back its DDL and version and closes the connection.
- `generated_answers`: one row per `cases.id`, a foreign key with `ON DELETE CASCADE`.
  The stored body is trimmed, non-empty, at most **1000 Unicode characters**, at most
  **4000 bytes**, with NUL rejected. SQL constraints back the length/byte/NUL boundary.
  It excludes presentation prefixes, receipt links, and fallback/error notices.
  Existing rows are not fabricated/backfilled from Discord and old confirmed cases
  remain valid without generated answers. There is no overwrite/retry version history.
- `generated_answer_sources`: at most three selected confirmed source IDs per answer.
  All evidence supplied to the provider is tracked, including sources it does not cite.
  A `BEFORE DELETE` trigger on `cases` removes generated bodies derived from a deleted
  source; foreign keys remove their links. This prevents retaining another user's
  deleted evidence merely because an already-generated draft belongs to someone else.
  This does not claim to identify independently human-written/copied summaries.
- Draft writes require an active, matching, uncancelled Store operation and an enabled
  scope. Under the write transaction they recheck candidate status, guild, parent
  channel, source conversation, author, and each confirmed source's tenant/existence.
  They never insert/resurrect a missing parent case or overwrite a human confirmation.
  Answer plus provenance links commit/roll back together. A storage error propagates;
  it is not swallowed as provider success. The earlier explicit question/history
  transaction remains if a provider fails or answer persistence fails.
- `Store.generated_answer(scope, case)` allows only the submitting user in the same
  guild/parent/conversation to read the draft. Moderator/admin status does not grant
  draft read/write access. This is a storage API, not a newly added public inbox command.
  Confirmed **human summaries** retain the existing parent-channel sharing semantics.
- The existing combined candidate+confirmed tenant cap also bounds the number of
  generated rows. Lowering the cap does not evict existing data. At capacity, attaching
  a draft to an admitted candidate or confirming it does not allocate another case.
  This is not a global tenant-count, physical SQLite-file, journal, or backup quota.

## Deletion and concurrency

`/privacy_delete`, `/forget`, channel disable, source single/bulk deletion, thread,
channel, and guild deletion remove linked generated rows in the same transaction as
the parent deletion. Deleting evidence also removes dependent generated bodies.
The existing pending-operation cancellation checks run before saving late provider
results, including reset/forget/privacy and gateway events. Disable/re-enable does not
revive an older operation. Unrelated users/tenants are not globally cancelled.

`/reset` deliberately keeps already-saved cases and draft answers, just as it keeps
confirmed cases. It clears the user's current conversation history and cancels an
in-flight result. Use privacy deletion or authorized forget for case/draft removal.

The supported runtime remains **one Store / one event loop / one bot process**.
SQLite write serialization, parent/source rechecks, foreign keys, and deletion trigger
also prevent resurrection in the tested competing-connection save/delete races.
They do **not** add a distributed revision/cancellation protocol: a reset in another
process cannot cancel this process's operation; delete-and-recreate of remote context
or unseen cross-process history changes are not a multi-instance guarantee.

Already-issued provider/Discord HTTP, delivered posts, remote retention, external
backups, and gateway events missed while offline are not rolled back or reconciled.
Secure deletion is enabled for local SQLite but is not a forensic wipe guarantee for
filesystem snapshots or backups. Retention periods and automated backup migrations
remain separate operational work. Do not run mixed or multi-instance writers as a
supported deployment strategy.

## Verification

The unchanged CI workflow automatically discovers these tests in its full Ubuntu
Python 3.11/3.12 suite; existing offline systemd normal/failure-recovery jobs remain.
No transport/fixture/workflow file owned by PR #11 was edited.

- `test_generated_answers.py`: populated pre-change schema migration, restart/idempotence,
  preserved IDs/confirmed data/history, unsupported schema rejection, and the Service
  candidate → explicit human resolution → future retrieval → privacy/reopen path.
- `test_generated_answer_limits.py`: Unicode/SQL bounds, invalid text/citations/evidence,
  tenant/user/conversation access, operation guard, no overwrite of confirmation,
  write/provenance/purge rollback, migration fault injection, capacity/restart, disabled
  and timed-out providers. Migration and answer fault injections use real SQLite.
- `test_generated_answer_privacy.py`: actual Discord command/raw deletion callbacks
  with real SQLite and only HTTP/provider fixtures; provider-await and post-save purge,
  reset semantics, selected evidence actually verified outside the provider, unrelated
  scope negatives, task cancellation, independent-connection rechecks, competing
  save/delete, and uncited-evidence deletion.
- `test_generated_answer_transport.py` plus `generated_answer_protocol_fixture.py`:
  real Service → real `CodexOAuthProvider` stdio subprocess → persisted synthetic answer
  → close/reopen → actual `/resolved` callback → cited retrieval → actual privacy command
  → close/reopen with no remaining case/history/answer/provenance. The readiness gate
  is replaced **only inside this test**, with a deterministic protocol fixture, never a
  real authenticated Codex process. It is not evidence of live model success.

Local macOS Python 3.9 full execution: **329 passed, 1 skipped** (Linux-only test),
plus successful `compileall` and `git diff --check`. Test-first failures were observed
for missing persistent access, schema version handling, retained evidence-derived
answers, malformed outputs/citations, and SQL NUL/size bypass before implementing fixes.
Exact pushed head/CI evidence belongs to the PR check records, not a self-referential
commit hash in this document. Independent review is requested from the parent agent;
this worker does not merge.
