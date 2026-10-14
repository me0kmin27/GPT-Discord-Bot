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

This branch contains the merged PR17 warning validation and sanitization. The
minimal deployment delta from that base changes exactly:

- `helperbot/codex_transport.py`
- `helperbot/provider.py`
- `helperbot/manage.py`

Do not blindly `git apply` over the installed transport's in-file model/effort
hotfix. First migrate those nonsecret settings into runtime.json as above,
retaining the actual guild. Stage the exact reviewed files and back up only the
three existing source files and private runtime config. The staged transport
contains PR17's warning shape/scope validation; it must replace, not erase, that
compatibility fix. Keep backups private. Never touch the Codex home/auth or DB.

For a **clean PR17 source checkout**, the generated code-only artifact can be
checked/applied with:

```sh
git apply --check /path/to/codex-web-search-minimal.patch
git apply /path/to/codex-web-search-minimal.patch
```

For an installed source tree with known local hotfixes, parent can stage reviewed
modules from the fetched exact head before replacing those three paths:

```sh
# In the fetched repository, after verifying HEAD equals the reviewed PR head:
stage=$(mktemp -d "$HOME/.cache/codex-web-stage.XXXXXX")
git archive HEAD helperbot/codex_transport.py helperbot/provider.py helperbot/manage.py |
  tar -x -C "$stage"
# Stop the user service, back up the three installed files/config, then copy
# these exact modules to the actual imported app directory. Do not rerun installer.
# Add codex settings to existing runtime.json, preserving sync_guild and mode 600.
# Run installed Python's offline management check before restarting:
# <installed-python> -m helperbot.manage run --check
# systemctl --user restart discord-helper.service
```

Parent must verify the actual imported module path, compare staged/installed file
hashes, read back only the three nonsecret Codex settings, and exercise a real
weather/current-question turn and candidate persistence with the already
operator-authorized app session. No live credentials or turns were used by this
implementation worker. On failure restore the private source/config backup and
restart; auth/DB are untouched. PR18 diagnostic tooling is a separate integration;
its direct provider construction must pass the runtime Codex options if used to
reproduce this configured service behavior.

## Verification scope

Deterministic subprocess tests exercise search/open/find/other actions, null
started actions, turn snapshots, malformed actions, wrong scope, local-tool and
server-request rejection, source limits, empty evidence generation/storage,
no-source and failed-search fallbacks, cancellation and privacy deletion/reset/
disable races. Existing signed-out/protocol/frame bounds remain tested.

Tests are synthetic, **not live weather/search accuracy evidence**. GitHub source
implements the requested selections; actual runtime parity requires parent
application of the three modules and runtime settings, plus live verification.
