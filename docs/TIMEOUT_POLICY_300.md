# 60/240-second timeout policy verification

Base: `12a3d3c` (local branch `feat/timeout-300`). This is an offline source-policy
change, not deployment evidence or proof of a historical live-timeout root cause.
The authoritative current configuration contract is [timeout-contract.md](timeout-contract.md).

## Policy and scope

- Preparation defaults to and permits at most 60 seconds; generation defaults to
  and permits at most 240 seconds. The work-budget sum is 300 seconds.
- Provider constructors, runtime options and the low-level transport use the shared
  validator. CLI/GUI settings retain their existing shared validation path.
- Generation starts with its own fresh budget after preparation. Unused preparation
  time is not transferred. Cleanup remains outside the phase budgets; there is no
  new total timer or fixed delay. Non-phased Service/probe timers are unchanged.
- GUI help/bounds, current documentation, the operator example, default readback
  assertions and numeric-boundary tests reflect the policy. Explicit legacy values
  remain valid and are not silently overwritten. Historical investigation evidence
  is retained and labeled as historical.

## Executed verification

Python 3.13.5, isolated scratch virtualenv, project installed editable with
`.[test,web]`. System Python lacked ensurepip; pip was bootstrapped only into the
scratch virtualenv, without changing system packages.

TDD regressions were observed before their respective production edits:

1. Provider-default regression: failed with `assert 3 == 60`; passed after updating
   defaults and constructor/shared-validator ceilings.
2. Low-level transport-default regression: failed with `assert 20 == 240`
   (22 other policy cases passed); then all 23 policy cases passed.
3. Rendered GUI regression: failed because the setup control lacked `max="60"`;
   passed after updating numeric bounds and Korean policy help.

Completed targeted run:

```text
python -m pytest tests/test_timeout_policy.py tests/test_phase_deadlines.py \
  tests/test_timeout_provenance.py tests/test_web_admin.py \
  tests/test_settings_ops.py tests/test_gui_cli.py \
  tests/test_codex_selection.py tests/test_codex_web_search.py -q
153 passed in 65.48s
```

Completed full run:

```text
python -m pytest -q --durations=12
612 passed in 448.14s (0:07:28)
```

The virtual-clock test exercises 59 seconds of preparation, 239 seconds of
generation and 10 seconds of cleanup successfully through real Service/SQLite.
Overrun cases check preparation 61 seconds (no turn/start) and generation 241
seconds after either 59 or 1 seconds of preparation, including safe budget labels.
Boundary tests exercise exact maxima, fractions, immediately above-max values,
nonfinite numbers and invalid types. GUI/CLI/runtime readback and preservation of
omitted and explicit values are covered.

`git diff --check` passed. Added-line scans found no assigned credentials, shell
injection, eval/exec, unsafe deserialization or SQL interpolation patterns.

Earlier full-suite attempts were interrupted (the first at a 180-second tool
limit); stale 121-second rejection and example-dictionary assertions were corrected
before the completed full run. The final run's slowest test was unrelated SQLite
window coverage (179.94 seconds); the existing provider cancellation-boundary test
now exercises the real 60-second preparation timeout (60.24 seconds).

## Limits

- No authenticated Codex inference, Discord delivery, remote server changes,
  installed runtime edits, service restart, push or PR was performed.
- The standalone Playwright browser smoke assertions were updated, but the browser
  smoke script and screenshots were not rerun; pytest's rendered-form and HTTP
  tests passed. Historical screenshots are not evidence of the new policy.
- Cross-version CI, signed-out real Codex protocol probes and disposable systemd
  lifecycle jobs were not run here. Local pytest is not a substitute for them.
- Deployment must separately set/reset stored overrides as intended and verify
  the running process uses 60/240. Longer budgets do not guarantee visible delivery
  within 300 seconds or establish that any earlier live failure is fixed.
