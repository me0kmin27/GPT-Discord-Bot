# Timeout investigation and phase-budget evidence

Base: `a256f4d` (PR #19). Investigation did not access live auth, conversations or
runtime databases, install packages, deploy code, or make authenticated inference.

## Findings versus hypotheses

- The supplied exact Discord fallback wording identifies the old Service
  `except (ProviderUnavailable, asyncio.TimeoutError)` timeout branch. It is not
  an initial interaction-acknowledgement failure or an admission denial.
- In the old implementation, `wait_owned` raises the same exception class for its
  own expired wait and propagates an immediately failing child's TimeoutError.
  The service labels both identically. Python 3.13 aliases native TimeoutError
  and asyncio.TimeoutError; older Python versions also had inconsistent native
  timeout mapping through the transport's OSError handlers.
- Deterministic tests reproduced this diagnostic ambiguity with a child failing
  immediately under a 20-second outer budget. This does **not** demonstrate that
  an immediate native timeout caused the reported live failure.
- No concrete arithmetic defect making the old configured 20-second timer expire
  early was established. The historical elapsed time was not measured. Parent's
  separately reported successful live probes do not reproduce that failure.
- RPC/receive used one absolute transport deadline, not a fresh budget for each
  notification. Initial Discord send/original-response precede Service inference.
  Admission denies before inference with a distinct request-limit message. Ack
  failure tests prove no provider call or case persistence occurs on that path.
- Empty knowledge does not gate generation. The former suggestion to change
  keywords or register a resolved case after provider failure was misleading as
  a remedy. Failure text now separates missing matches from provider failure.

## Newly approved behavior (not a proven historical root-cause fix)

Preparation receives at most 3 seconds; after verified thread creation, generation
receives its own 20 seconds, including turn/start and hosted search. No fixed
3-second sleep. Phase-managed providers are no longer raced by Service/probe's
old total-20-second timer. The request's cancellation owner still settles all
work/cleanup. Full configuration contract is in `timeout-contract.md`.

Safe diagnostics distinguish owned expiry (`deadline_exceeded`) from child/native
failure (`timeout`) and include known stage, monotonic elapsed and configured
budget. Native errors are handled consistently on Python 3.9 and 3.13. Exceptions
are never stringified for diagnostic output.

## Verification

- RED on original behavior: owned-versus-immediate distinction and fallback text;
  three assertions failed, including the native TimeoutError difference on 3.9.
- RED on old budget policy: virtual-clock setup 2 seconds + generation 19 seconds
  was cut by Service's total-20-second guard; a 4-second preparation incorrectly
  succeeded, and a generation timeout had only a provider-wide label.
- GREEN tests use virtual monotonic time, real Service/SQLite and fake protocol
  boundaries. They prove setup 2 + generation 19 succeeds/persists, setup 4 times
  out without turn/start, and generation 21 times out under its own 20-second
  budget. Actual subprocess fixtures separately verify cleanup/cancellation.
- CI includes Python 3.9/3.11/3.12/3.13, pinned signed-out Codex protocol,
  clean installer, and both disposable systemd lifecycle scenarios. Check the
  final PR head's actual checks; local passing tests alone are not full CI.

## Remaining live acceptance

The parent/operator owns independent review, merge, installed-file dependency
reconciliation and deployment. Upgrade async_utils, codex_transport, service and
inference_probe together; copying only one would create a mixed-version import
or deadline mismatch. Preserve operator model, effort, web-search and guild values.
After deployment, confirm the actual command path and safe timing labels. Do not
claim the earlier live symptom fixed without live observation. No original prompt,
answer, raw exception, auth, or database dump is required; if failure recurs, the
fixed stage/category/origin and numeric elapsed/budget fields are sufficient for
initial correlation.
