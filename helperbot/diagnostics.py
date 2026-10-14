"""Allowlisted diagnostic data only; never stringify a third-party exception."""
import json

import discord


NEUTRAL_HINT = 'Cause not determined. Review this stage and numeric codes locally; do not share credentials or raw logs.'
# Meanings verified against Discord's official JSON Error Codes reference:
# https://docs.discord.com/developers/topics/opcodes-and-status-codes#json
GUILD_HINTS = {
    50001: 'Missing access. Verify the configured guild ID and that the same Discord application/bot is installed and authorized there; these are checks, not a confirmed cause.',
    50013: 'Missing permissions for this action. Review the application authorization and required permissions in the selected guild; do not bypass permission checks.',
    10004: 'Unknown guild. Verify the configured server (guild) ID against the intended server locally.',
}


def diagnostic(stage, error):
    category = 'Other'
    for cls, label in ((discord.Forbidden, 'Forbidden'), (discord.NotFound, 'NotFound'),
                       (discord.HTTPException, 'HTTPException'), (discord.LoginFailure, 'LoginFailure'),
                       (TimeoutError, 'TimeoutError'), (OSError, 'OSError')):
        if isinstance(error, cls):
            category = label
            break
    status = code = None
    if isinstance(error, discord.HTTPException):
        # No coercion: strings, bools, int subclasses and unbounded values are not safe metadata.
        if type(error.status) is int and 100 <= error.status <= 599:
            status = error.status
        if type(error.code) is int and 0 <= error.code <= 2**31 - 1:
            code = error.code
    stage = stage if stage in ('guild_sync', 'global_sync', 'discord_login', 'operation') else 'operation'
    return json.dumps({'event': 'operation_failed', 'stage': stage, 'exception': category,
                       'http_status': status, 'discord_code': code,
                       'hint': GUILD_HINTS.get(code, NEUTRAL_HINT) if stage == 'guild_sync' else NEUTRAL_HINT})


class StartupFailure(RuntimeError):
    """Carry only a sanitized record across the CLI boundary."""
    def __init__(self, stage, error):
        super().__init__(diagnostic(stage, error))
