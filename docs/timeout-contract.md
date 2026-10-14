# Timeout configuration contract

CLI and future GUI must share `helperbot.codex_transport.validate_options`; do not duplicate validation. Runtime loading already calls that validator for `runtime.json.codex`.

Shared default constants: `DEFAULT_SETUP_TIMEOUT` and `DEFAULT_GENERATION_TIMEOUT` in that same module. Leave omitted settings omitted when saving unrelated fields; preserve other operator options.

```json
{
  "provider": "codex-oauth",
  "sync_guild": null,
  "codex": {
    "setup_timeout_seconds": 3,
    "generation_timeout_seconds": 20
  }
}
```

- `setup_timeout_seconds`: default **3**, exact Python int/float (JSON number), finite, **0 < value <= 30** seconds.
- `generation_timeout_seconds`: default **20**, exact Python int/float (JSON number), finite, **0 < value <= 120** seconds.
- Reject bool, string, null, zero, negative, NaN, infinity, out-of-range numbers, and unknown keys. Fractions are allowed; omission selects the default.
- These are application deadlines, never forwarded as Codex CLI `-c` settings. Existing `web_search`, `model`, `model_reasoning_effort` options are unchanged.
- Preparation includes isolated request directory/process setup, initialize, config validation, account check, and thread/start plus thread validation. It is a maximum duration, **not a fixed sleep**.
- Once preparation succeeds, generation gets its own fresh budget for turn/start and complete validated output, including hosted web search. Unused setup time is not added to generation.
- Service and inference probe must not put the old competing total-20-second deadline around a phase-managed provider. Non-phased providers retain Service's default 20-second budget; an explicit Service timeout remains an override for tests/custom callers.
- Deadline expiry cancels and settles owned tasks, kills/reaps the request process and removes its temporary directory. Cleanup is outside the work budgets and may delay visible delivery. These are cooperative asyncio deadlines, not hard real-time guarantees during blocked event-loop/OS work.

Diagnostics distinguish application-owned expiry from an immediate child/native TimeoutError. Safe output contains only fixed stage/category/origin labels, monotonic elapsed milliseconds and configured budget milliseconds; never exception strings, prompts, answers, credentials, query text, or protocol frames. `deadline_ms` is a duration budget, not a wall-clock timestamp. A child/native timeout is not proof that the configured budget elapsed.

This change implements a newly approved budget policy. It does not prove the cause of any previously reported live timeout or that the live symptom has been fixed.
