# Explicit Codex OAuth web search (0.162.1)

## Operator selection

Managed ChatGPT OAuth remains the only supported enabled provider. This does not
add an API key, copy login credentials, or enable local shell/network execution.
Old runtime files remain valid; search defaults to **disabled**. In the existing
private `runtime.json`, preserve `provider` and the actual `sync_guild`, and add:

```json
"codex": {
  "web_search": "live",
  "model": "gpt-6.1-sol",
  "model_reasoning_effort": "low"
}
```

The model/effort above are the operator's requested nonsecret selections, **not
universal defaults or an assertion of availability for other accounts**. Omit
model/effort to use official defaults. Only `disabled`/`live` search and bounded
model/effort identifier strings are accepted; arbitrary Codex configuration is
rejected. Settings are checked against `config/read`. Keep runtime.json private
(mode 600, same owner); never put auth.json, tokens, credentials, or databases in
Git. The `discord-helper run` service path reads these settings; direct
`CodexOAuthProvider(..., options=...)` callers must pass them explicitly.

`examples/runtime.codex-web-search.json` is a nonsecret template; its null guild
means global registration and must NOT replace the operator's existing guild.

## Pinned primary-source contract

Inspected OpenAI `openai/codex` tag `rust-v0.162.1`, resolved commit
`092d3acd6bec3e3a14bdc7e7a2810ab628ab759d`:

- `codex-rs/core/config.schema.json`: `web_search` modes include `live`;
  `model` is a string and `model_reasoning_effort` a nonempty string.
- `codex-rs/ext/web-search/src/extension.rs`: live mode maps to external web
  access true at the OpenAI search service; this is not the local sandbox's
  `networkAccess` switch. Model metadata/feature selection can choose the
  official standalone search executor instead of the hosted Responses tool.
- `codex-rs/app-server-protocol/schema/typescript/WebSearchItem.ts` and
  `v2/WebSearchAction.ts`: item has id, query, nullable action/results. Actions
  are search (nullable query/queries), openPage, findInPage, other.
- `codex-rs/app-server/tests/suite/v2/web_search.rs`: started item can have empty
  query/null action/results; completed item carries the action and optional
  opaque results. There is **no webSearch status field**; lifecycle is
  `item/started` / `item/completed`, within the turn's status lifecycle.
- `codex-rs/app-server-protocol/schema/typescript/v2/ThreadItem.ts`: agentMessage
  text has no dedicated URL-citation annotation field. Our `web_sources` array
  is an application output-schema contract, not an upstream guarantee of
  fetched/verified URLs.

Browse those paths at `https://github.com/openai/codex/tree/rust-v0.162.1`.

## Bounds and trust

Only explicit live mode admits webSearch item envelopes. Query/result bodies
are shape-checked and discarded before notification buffering; they are never
logged, persisted as evidence, or interpreted as final answers. Completed
agentMessage/final_answer JSON plus successful turn completion is still required.
All server requests (including web-shaped requests), local tool items and
unknown methods fail closed. Frame/wire/event/queue limits are unchanged.

Shell, browser, computer, MCP, plugins, local tools and approval controls remain
restricted. The local sandbox stays read-only with networkAccess=false.
Post-execution event rejection is detection, not proof of zero registered tools;
read-only sandboxing does not deny all host reads. Hosted search may transmit
model-selected queries to OpenAI/search providers. The instruction requests
query minimization and forbids private evidence/history in queries; this is not
a deterministic DLP boundary. Do not promise that a remote search can be recalled
once submitted. Cancellation kills/reaps the owned local process and prevents
late answer persistence; it cannot undo a remote request already received.

The final structured output in live mode requires `text`, `case_ids`, and
`web_sources`. Up to three HTTP(S) URLs are accepted only after a completed search
item. This proves only that a search event completed, not that each URL was
fetched, supports the claim, or is safe. The application does not fetch these
URLs. It labels them **Model-cited web sources (not independently verified)**.
No sources yields **No web sources supplied; current facts unverified**. A
failed/malformed turn produces the existing no-generation fallback, not weather
invented from case retrieval. Case IDs remain restricted to supplied confirmed
cases. Rendered answer including URL labels must fit the existing 1000-character
storage limit; oversize output fails closed rather than stripping provenance.
Generated text remains a candidate until explicit human resolution.

## Parent-operated minimal apply / rollback

The three-module **PR source delta** is relative to main `5687dfe1` (PR17 and
PR18), not the installed `f1c0957` baseline. It changes:

- `helperbot/codex_transport.py`
- `helperbot/provider.py`
- `helperbot/manage.py`

For the supplied installed `f1c0957` plus warning/model hotfixes, the minimum
reviewed replacement manifest is **four modules**: those three plus
`helperbot/diagnostics.py`. New `manage.py` imports that module; the old baseline
has no such file. `helperbot/async_utils.py` already exists and is byte-identical
to the reviewed source at that baseline. Verify this against the actual installed
files and dependencies rather than assuming that local drift matches Git.

Do not blindly apply a three-file patch or rerun the installer. Parent must:

1. Reconcile the actual imported app directory and installed Python with the
   supplied baseline. Stage all four exact-reviewed modules into a disposable
   reconstruction of that baseline and inspect local hotfix drift. If the baseline
   or dependencies differ, stop and review the complete replacement package.
2. Prepare a private runtime config preserving actual `provider` and `sync_guild`;
   migrate the in-file model/effort overrides to `gpt-6.1-sol` / `low`, with explicit
   `web_search: live`. Never substitute the example's null guild. Review this
   prepared config before live installation. Preserve the integrated warning fix.
3. Before replacement, stop the service and privately back up every replaced file
   and runtime.json, recording whether each file originally existed. The manifest
   includes diagnostics.py even when it is newly added. Keep source and config
   backups paired, mode 600 for config, with unchanged ownership.
4. Copy the four exact modules only after prerequisite review. Compare installed
   hashes to staged hashes and verify the actual imported module paths. Do not
   read/copy/change credentials, Codex auth/home, or the active database.
5. Run imports and offline checks using installed Python but **isolated temporary
   config/data/unit paths**, then restart only after they pass. Bare `run --check`
   opens Store on the configured database; it is NOT a read-only live DB check.

Staging from the fetched, exact-reviewed head (not a live installation command):

```sh
umask 077
stage=$(mktemp -d "$HOME/.cache/codex-web-stage.XXXXXX")
git archive HEAD helperbot/codex_transport.py helperbot/provider.py \
  helperbot/manage.py helperbot/diagnostics.py | tar -x -C "$stage"
```

For the isolated check, create another private temporary directory, put only the
reviewed nonsecret runtime.json into its `config` directory (mode 600), and use
all three explicit paths. Run from the reconstructed/staged full app directory,
not the repository checkout, and verify imports resolve there:

```sh
# probe is a new private temporary directory, NOT the active runtime directory.
# installed_python is the verified installed venv interpreter.
"$installed_python" -m helperbot.manage \
  --config-dir "$probe/config" --data-dir "$probe/data" \
  --unit-dir "$probe/units" run --check
```

The temporary data directory may need a reference to the verified installed Codex
executable under `tools/node_modules/.bin/codex` (or its directory on PATH);
never point the probe data path at the live data directory to satisfy discovery.
This check does not authenticate or prove model/search availability.

On failure, keep the service stopped while restoring **both source and the old
runtime.json** before restarting: the old parser rejects the new `codex` key.
Remove newly added diagnostics.py if absent in the recorded pre-install state;
restore existing files otherwise. Verify restored hashes/config before restart.
Auth and DB stay untouched. A four-module mixed-version overlay does **not**
install full PR18 diagnostics: old service.py/discord_app.py remain unchanged.
Do not claim full-tree runtime parity. Direct diagnostic provider construction
must pass runtime Codex options explicitly.

Parent alone operates the live session. After successful staging/installation,
read back only nonsecret option values and guild preservation, verify stable
service status (including restart count), and exercise an operator-authorized
current/weather turn with candidate persistence. No live credentials, service
operations, or turns were used by this implementation worker.

## Verification scope

Deterministic subprocess tests exercise search/open/find/other actions, null
started actions, turn snapshots, malformed actions, wrong scope, local-tool and
server-request rejection, source limits, empty evidence generation/storage,
no-source and failed-search fallbacks, cancellation and privacy deletion/reset/
disable races. Existing signed-out/protocol/frame bounds remain tested.

### Reconstructed-baseline deployment evidence

The documentation correction was checked against production source at
`b2dd5c292e4e9772653a6b4acff1681cdafdc654`; production source is unchanged by
this correction. A disposable `git archive f1c0957` reconstruction was overlaid
with exact reviewed modules using Python 3.9.6 and installed test dependencies:

- Three modules: import failed with `ModuleNotFoundError: helperbot.diagnostics`.
- Four modules (including diagnostics.py): imports passed, exit 0.
- Baseline async_utils.py compared byte-for-byte equal to reviewed source.
- Four-module `run(Paths(...), check=True, codex_executable=...)`: exit 0 for
  both legacy provider/guild config and the new Codex config. Each used private
  scratch config/data/units, never the active database. The executable argument
  was the test Python interpreter, a deliberate executable-discovery fixture;
  this did not execute Codex or prove authentication.
- Synthetic guild `123`, model `gpt-6.1-sol`, effort `low`, and search `live`
  round-tripped unchanged. Actual installed hotfix drift was not inspected.

This is explicit one-off reconstruction evidence, not a new automated CI test;
normal shallow CI checkouts do not supply the historical baseline. The existing
full-tree suite does not by itself validate mixed-version deployment.

Tests are synthetic, **not live weather/search accuracy evidence**. Applying the
four-module overlay and reviewed runtime settings still requires parent-only
live verification; it does not establish full source/runtime parity.
