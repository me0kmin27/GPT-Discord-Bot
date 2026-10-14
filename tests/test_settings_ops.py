import json
import os
import pytest
from helperbot.manage import Paths, ManagementError


def paths_at(tmp_path):
    paths = Paths(tmp_path/'config', tmp_path/'data', tmp_path/'units')
    paths.config.mkdir(mode=0o700)
    target = paths.config/'runtime.json'
    target.write_text(json.dumps({'provider': 'codex-oauth', 'sync_guild': 123,
                                 'codex': {'web_search': 'live'}}))
    target.chmod(0o600)
    return paths


def test_shared_atomic_save_preserves_existing_options(tmp_path):
    from helperbot.settings_ops import read_settings, save_settings
    paths = paths_at(tmp_path)
    before = read_settings(paths)
    save_settings(paths, {'model': 'gpt-test'}, before['revision'])
    raw = json.loads((paths.config/'runtime.json').read_text())
    assert raw == {'provider': 'codex-oauth', 'sync_guild': 123,
                   'codex': {'web_search': 'live', 'model': 'gpt-test'}}
    assert (paths.config/'runtime.json').stat().st_mode & 0o777 == 0o600
    assert read_settings(paths)['values']['model'] == 'gpt-test'
    with pytest.raises(ManagementError):
        save_settings(paths, {'model': 'stale'}, before['revision'])
    with pytest.raises(ManagementError):
        save_settings(paths, {'provider': 'evil'}, read_settings(paths)['revision'])


def test_apply_requires_current_revision_and_explicit_confirmation(tmp_path):
    from helperbot.settings_ops import read_settings, apply_settings
    paths = paths_at(tmp_path)
    calls = []
    def runner(args, **kwargs):
        from subprocess import CompletedProcess
        calls.append(args)
        return CompletedProcess(args, 0, 'ActiveState=active\nSubState=running\nResult=success\nExecMainStatus=0\nNRestarts=0\n', '')
    rev = read_settings(paths)['revision']
    with pytest.raises(ManagementError):
        apply_settings(paths, rev, False, runner=runner)
    assert calls == []
    result = apply_settings(paths, rev, True, runner=runner)
    assert calls[0] == ['systemctl', '--user', 'restart', 'discord-helper.service']
    assert result['ActiveState'] == 'active'
    assert 'applied' not in result


def test_timeout_defaults_and_validation_use_provider_contract(tmp_path):
    from helperbot.settings_ops import read_settings, save_settings
    from helperbot.codex_transport import DEFAULT_SETUP_TIMEOUT, DEFAULT_GENERATION_TIMEOUT
    paths = paths_at(tmp_path)
    shown = read_settings(paths)
    assert shown['values']['setup_timeout_seconds'] == DEFAULT_SETUP_TIMEOUT
    assert shown['values']['generation_timeout_seconds'] == DEFAULT_GENERATION_TIMEOUT
    for value in (True, '3', float('nan'), float('inf'), 0, 31):
        with pytest.raises(ManagementError):
            save_settings(paths, {'setup_timeout_seconds': value}, shown['revision'])
    saved = save_settings(paths, {'setup_timeout_seconds': 2.5, 'generation_timeout_seconds': 21}, shown['revision'])
    assert saved['values']['setup_timeout_seconds'] == 2.5
    assert saved['values']['generation_timeout_seconds'] == 21
