"""Installer boundaries; fixture credentials never represent live readiness."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from helperbot import manage as m

ROOT = Path(__file__).resolve().parents[1]


def test_preflight_rejects_root_and_missing_dependencies(monkeypatch):
    from helperbot import bootstrap as b
    monkeypatch.setattr(b.sys, 'platform', 'linux')
    monkeypatch.setattr(b.os, 'getuid', lambda: 0)
    with pytest.raises(b.InstallError, match='non-root'):
        b.preflight(False)
    monkeypatch.setattr(b.os, 'getuid', lambda: 1000)
    monkeypatch.setattr(b.shutil, 'which', lambda name: None)
    with pytest.raises(b.InstallError, match='git'):
        b.preflight(False)


def test_checkout_pins_commit_and_refuses_unowned_or_changed_source(tmp_path):
    from helperbot import bootstrap as b
    source = tmp_path/'source'
    source.mkdir()
    subprocess.run(['git', 'init', str(source)], check=True, capture_output=True)
    subprocess.run(['git', '-C', str(source), 'config', 'user.email', 'fixture@example.invalid'], check=True)
    subprocess.run(['git', '-C', str(source), 'config', 'user.name', 'Fixture'], check=True)
    (source/'file').write_text('pinned')
    subprocess.run(['git', '-C', str(source), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(source), 'commit', '-m', 'fixture'], check=True, capture_output=True)
    root = tmp_path/'install'
    checkout = b.prepare_checkout(source, root)
    assert (checkout/'file').read_text() == 'pinned'
    assert b.prepare_checkout(source, root) == checkout
    original_marker = (root/'installer.json').read_bytes()
    (source/'file').write_text('new reviewed revision')
    subprocess.run(['git', '-C', str(source), 'commit', '-am', 'next'], check=True, capture_output=True)
    with pytest.raises(b.InstallError, match='no automatic upgrades'):
        b.prepare_checkout(source, root)
    assert (root/'installer.json').read_bytes() == original_marker
    assert (checkout/'file').read_text() == 'pinned'
    subprocess.run(['git', '-C', str(source), 'checkout', '--detach', 'HEAD~1'], check=True, capture_output=True)
    (checkout/'file').write_text('operator edit')
    with pytest.raises(b.InstallError, match='changed'):
        b.prepare_checkout(source, root)
    unowned = tmp_path/'unowned'
    unowned.mkdir()
    (unowned/'keep').write_text('mine')
    with pytest.raises(b.InstallError, match='Unowned'):
        b.prepare_checkout(source, unowned)
    assert (unowned/'keep').read_text() == 'mine'


def test_interactive_finish_preserves_settings_and_stops_on_login_failure(tmp_path, monkeypatch):
    from helperbot import bootstrap as b
    paths = m.Paths(tmp_path/'config', tmp_path/'data', tmp_path/'units')
    calls = []
    monkeypatch.setattr(b, 'ask', lambda message: '123')
    monkeypatch.setattr(m, 'setup', lambda paths: calls.append('setup'))
    monkeypatch.setattr(m, 'load_token', lambda paths: 'fixture-only')
    monkeypatch.setattr(b, 'oauth_ready', lambda paths: False)
    monkeypatch.setattr(m, 'codex_login', lambda paths: 1)
    monkeypatch.setattr(m, 'install', lambda paths: calls.append('install'))
    with pytest.raises(b.InstallError, match='OAuth'):
        b.finish(paths)
    assert calls == ['setup']
    assert json.loads((paths.config/'runtime.json').read_text()) == {'provider': 'codex-oauth', 'sync_guild': 123}
    before = (paths.config/'runtime.json').read_bytes()
    # A resume must preserve explicit defaults and non-default nested choices too.
    selected = json.loads(before)
    selected['codex'] = {'model': 'fixture-model', 'model_reasoning_effort': 'low',
                         'web_search': 'live', 'setup_timeout_seconds': 3,
                         'generation_timeout_seconds': 45}
    (paths.config/'runtime.json').write_text(json.dumps(selected) + '\n')
    before = (paths.config/'runtime.json').read_bytes()
    monkeypatch.setattr(b, 'oauth_ready', lambda paths: True)
    monkeypatch.setattr(b, 'offline_check', lambda *a, **kw: None)
    monkeypatch.setattr(m, 'lifecycle', lambda paths, action: calls.append(action) or 0)
    monkeypatch.setattr(b, 'service_readback', lambda: calls.append('readback'))
    b.finish(paths)
    assert (paths.config/'runtime.json').read_bytes() == before
    assert calls[-4:] == ['install', 'start', 'status', 'readback']
    monkeypatch.setattr(m, 'lifecycle', lambda paths, action: 1)
    with pytest.raises(b.InstallError, match='ExecMainStatus'):
        b.finish(paths)
    assert (paths.config/'runtime.json').read_bytes() == before


def test_service_runtime_config_selects_provider_and_guild(tmp_path, monkeypatch):
    paths = m.Paths(tmp_path/'config', tmp_path/'data', tmp_path/'units')
    paths.config.mkdir()
    (paths.config/'runtime.json').write_text(json.dumps({'provider': 'codex-oauth', 'sync_guild': 123}))
    (paths.config/'runtime.json').chmod(0o600)
    selected = []
    monkeypatch.setattr(m, 'build_provider', lambda name, **kw: selected.append(name))
    class Client:
        def run(self, token, **kw): pass
    monkeypatch.setattr(m, 'create_client', lambda store, **kw: selected.append(kw['sync_guild']) or Client())
    monkeypatch.setattr(m, 'load_token', lambda paths: 'fixture-only')
    assert m.run(paths) == 0
    assert selected == ['codex-oauth', 123]


@pytest.mark.parametrize('config', [
    {'provider': 'api-key', 'sync_guild': 123},
    {'provider': 'codex-oauth', 'sync_guild': True},
    {'provider': 'codex-oauth', 'sync_guild': 0},
    {'provider': 'codex-oauth', 'sync_guild': -1},
    {'provider': 'codex-oauth', 'sync_guild': '123'},
    {'provider': 'codex-oauth', 'sync_guild': 2**64},
    {'provider': 'codex-oauth', 'sync_guild': 123, 'unknown': True},
])
def test_runtime_config_rejects_unsafe_values(tmp_path, config):
    paths = m.Paths(tmp_path, tmp_path/'data', tmp_path/'units')
    (tmp_path/'runtime.json').write_text(json.dumps(config))
    (tmp_path/'runtime.json').chmod(0o600)
    with pytest.raises(m.ManagementError):
        m.runtime_config(paths)


def test_prepare_software_refuses_unowned_tools(tmp_path, monkeypatch):
    from helperbot import bootstrap as b
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path/'data'))
    tools = tmp_path/'data/discord-helper/tools'
    tools.mkdir(parents=True)
    (tools/'precious').write_text('keep')
    root = tmp_path/'install'
    root.mkdir()
    with pytest.raises(b.InstallError, match='tools'):
        b.prepare_software(tmp_path/'checkout', root)
    assert (tools/'precious').read_text() == 'keep'


def test_installer_offline_check_does_not_open_live_database(tmp_path):
    from helperbot import bootstrap as b
    paths = m.Paths(tmp_path/'config', tmp_path/'data', tmp_path/'units')
    native = paths.data/'tools/node_modules/@openai/codex-fixture/vendor/fixture/bin/codex'
    native.parent.mkdir(parents=True)
    native.write_text('fixture native discovery only')
    database = paths.data/'state.db'
    database.write_bytes(b'LIVE DB MUST NOT BE OPENED OR CHANGED')
    with m.runtime_lock(paths):
        b.offline_check(paths)
    assert database.read_bytes() == b'LIVE DB MUST NOT BE OPENED OR CHANGED'


def test_oauth_status_never_accepts_api_key_or_leaks_output(tmp_path, monkeypatch, capsys):
    from helperbot import bootstrap as b
    paths = m.Paths(tmp_path/'config', tmp_path/'data', tmp_path/'units')
    m.private_dir(paths.data/'codex')
    (paths.data/'codex/auth.json').write_text('{}')
    (paths.data/'codex/auth.json').chmod(0o600)
    calls = []
    def runner(args, **kw):
        calls.append((args, kw))
        return subprocess.CompletedProcess(args, 0, 'Logged in using an API key: fixture-secret', '')
    monkeypatch.setattr(b.subprocess, 'run', runner)
    monkeypatch.setenv('OPENAI_API_KEY', 'fixture-secret')
    assert not b.oauth_ready(paths)
    assert 'OPENAI_API_KEY' not in calls[0][1]['env']
    assert 'fixture-secret' not in capsys.readouterr().out


def test_installer_help_is_read_only_and_rejects_unknown_args(tmp_path):
    env = dict(os.environ, HOME=str(tmp_path), PATH=str(Path(sys.executable).parent) + os.pathsep + os.environ['PATH'])
    result = subprocess.run(['bash', str(ROOT/'install.sh'), '--help'], env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert '--prepare-only' in result.stdout
    assert 'not an upgrade command' in result.stdout
    assert 'docs/UPGRADE_KO.md' in result.stdout
    assert 'Web GUI' in result.stdout
    assert not (tmp_path/'.local').exists() and not (tmp_path/'.config').exists()
    result = subprocess.run(['bash', str(ROOT/'install.sh'), '--unknown'], env=env, text=True, capture_output=True)
    assert result.returncode != 0
    assert not (tmp_path/'.local').exists() and not (tmp_path/'.config').exists()
