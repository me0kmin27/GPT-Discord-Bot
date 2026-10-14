# Safe startup diagnosis

The management CLI emits one JSON error record on failed Discord login or command
sync, with `stage`, an allowlisted `exception` category, `http_status` and
`discord_code` (null when unavailable), and a fixed hint. It does not emit raw
exception messages, response bodies, headers, URLs, tokens or traceback content.
Unknown exception classes are `Other`; unknown codes receive a neutral hint.
Failures still exit nonzero. Guild failures never fall back to global sync.

Stages distinguish `discord_login`, `guild_sync`, and `global_sync`. Other
uncategorized CLI failures use `operation`; that is not a diagnosis of their
cause. `setup_hook` executes inside Discord login, but a sync failure retains its
sync stage rather than being mislabeled as authentication failure.

For guild sync only, fixed hints use the official Discord JSON error meanings:

- 50001: Missing access. Check the configured guild ID and installation and
  authorization of the same application/bot in that guild; none is a proven cause.
- 50013: You lack permissions to perform that action. Review authorization and
  required permissions, without bypassing checks or granting blanket admin access.
- 10004: Unknown guild. Verify the intended server ID locally.

Reference: https://docs.discord.com/developers/topics/opcodes-and-status-codes#json
Verified against the official `discord/discord-api-docs` source. HTTP 403 alone
does not identify which configuration is wrong. Do not reset unrelated Codex
OAuth credentials on the strength of a guild-sync failure.

## Minimal operator evidence

Run as the service's Linux user, not root:

```sh
systemctl --user show discord-helper.service --property=ActiveState,SubState,Result,ExecMainStatus,NRestarts
journalctl --user -u discord-helper.service -n 30 --no-pager
```

Inspect journal output **locally**. Share only the structured error's stage,
exception category, HTTP status and Discord code, and the five service properties
above. Do not paste raw journals, credentials, OAuth files, environment dumps or
tracebacks. Older installed revisions will still emit the generic error; this
repository fix does not update a pinned installation automatically.

An active snapshot is not sustained readiness. Inspect restart counts and service
result together. If foreground reproduction is necessary, stop the managed
instance first and use the installed launcher with its existing private paths;
do not start a competing checkout against the same database. Do not delete the
database or change provider authentication to diagnose command registration.

This change fixes suppressed diagnostics, not an unknown live host's guild
membership, application identity, server ID or authorization. No live Discord or
kuma access is assumed or verified.

## Regression evidence

The CLI guild-sync test first failed because stderr was the generic `Operation
failed` text instead of structured metadata. The login test separately failed
because its stage was `operation`. Installer tests failed on network-blaming text
and missing service-state guidance before their fixes. The tests inject failures
at Discord network boundaries while exercising the real CLI/client startup and
SQLite store, asserting nonzero return and no global fallback. Sensitive fake
bodies/headers/URLs, malformed numeric values and unknown exception names are not
rendered. These offline tests do not establish live Discord readiness.
