"""Offline startup boundary tests: no Discord requests or real credentials."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest

from helperbot import manage

SECRET = 'FAKE_TOKEN Authorization: Bearer private https://secret.invalid/?token=private'


def invoke(tmp_path, monkeypatch, failure, *, guild=123, login=False):
    monkeypatch.setenv('DISCORD_BOT_TOKEN', 'fake-token')
    calls = AsyncMock(side_effect=failure)
    if login:
        monkeypatch.setattr(discord.Client, 'login', calls)
    else:
        async def fake_login(self, token):
            await self.setup_hook()
        monkeypatch.setattr(discord.Client, 'login', fake_login)
        monkeypatch.setattr(discord.app_commands.CommandTree, 'sync', calls)
    args = ['--config-dir', str(tmp_path/'config'), '--data-dir', str(tmp_path/'data'), 'run']
    if guild is not None:
        args += ['--sync-guild', str(guild)]
    return manage.main(args), calls


def http_error(code=50001, status=403):
    return discord.Forbidden(SimpleNamespace(status=status, reason=SECRET, headers={'Authorization': SECRET}),
                             {'code': code, 'message': SECRET})


def test_guild_sync_failure_is_safe_and_nonzero(tmp_path, monkeypatch, capsys, caplog):
    result, calls = invoke(tmp_path, monkeypatch, http_error())
    captured = capsys.readouterr()
    assert result == 1
    assert calls.await_count == 1
    assert calls.call_args.kwargs['guild'].id == 123  # no global fallback
    assert SECRET not in captured.out + captured.err + caplog.text
    record = json.loads(captured.err)
    assert record['stage'] == 'guild_sync'
    assert record['exception'] == 'Forbidden'
    assert record['http_status'] == 403
    assert record['discord_code'] == 50001
    assert 'Missing access' in record['hint']


def test_login_failure_is_distinct(tmp_path, monkeypatch, capsys):
    result, calls = invoke(tmp_path, monkeypatch, discord.LoginFailure(SECRET), login=True)
    captured = capsys.readouterr()
    assert result == 1
    assert calls.await_count == 1
    assert SECRET not in captured.out + captured.err
    record = json.loads(captured.err)
    assert record['stage'] == 'discord_login'
    assert record['exception'] == 'LoginFailure'
    assert record['http_status'] is None
    assert record['discord_code'] is None


@pytest.mark.parametrize('guild,stage', [(None, 'global_sync'), (123, 'guild_sync')])
@pytest.mark.parametrize('code,meaning', [(50013, 'Missing permissions'), (10004, 'Unknown guild'),
                                          (987654, 'Cause not determined')])
def test_code_hints_are_stage_scoped(tmp_path, monkeypatch, capsys, guild, stage, code, meaning):
    result, calls = invoke(tmp_path, monkeypatch, http_error(code), guild=guild)
    record = json.loads(capsys.readouterr().err)
    assert result == 1 and calls.await_count == 1
    assert record['stage'] == stage
    assert (meaning if guild else 'Cause not determined') in record['hint']


@pytest.mark.parametrize('value', [SECRET, True, -1, 2**100, 403.0, None])
def test_untrusted_numeric_metadata_is_not_rendered(tmp_path, monkeypatch, capsys, value):
    error = http_error()
    error.status = error.code = value
    result, _ = invoke(tmp_path, monkeypatch, error)
    captured = capsys.readouterr()
    record = json.loads(captured.err)
    assert result == 1
    assert record['http_status'] is None and record['discord_code'] is None
    assert SECRET not in captured.out + captured.err


def test_unknown_exception_name_and_string_are_not_rendered(tmp_path, monkeypatch, capsys):
    class UnsafeError(Exception):
        def __str__(self):
            raise AssertionError('Must not stringify')
    UnsafeError.__name__ = SECRET
    result, _ = invoke(tmp_path, monkeypatch, UnsafeError(SECRET))
    captured = capsys.readouterr()
    record = json.loads(captured.err)
    assert result == 1
    assert record['exception'] == 'Other'
    assert record['hint'].startswith('Cause not determined')
    assert SECRET not in captured.out + captured.err


def test_installer_systemctl_failure_gives_safe_diagnosis(monkeypatch):
    from helperbot import bootstrap
    monkeypatch.setattr(bootstrap.subprocess, 'run', lambda *a, **k:
                        SimpleNamespace(returncode=3, stdout=SECRET, stderr=SECRET))
    with pytest.raises(bootstrap.InstallError) as caught:
        bootstrap.command(['systemctl', '--user', 'is-active', 'discord-helper.service'])
    text = str(caught.value)
    assert SECRET not in text
    assert 'network' not in text
    assert 'systemctl --user show discord-helper.service' in text
    assert 'stage' in text and 'raw logs' in text


def test_restart_during_readback_gives_same_safe_guidance(monkeypatch):
    from helperbot import bootstrap
    values = iter(['123', '', '456'])
    monkeypatch.setattr(bootstrap, 'command', lambda *a, **k: next(values))
    monkeypatch.setattr(bootstrap.time, 'sleep', lambda _: None)
    with pytest.raises(bootstrap.InstallError, match='ExecMainStatus'):
        bootstrap.service_readback()
