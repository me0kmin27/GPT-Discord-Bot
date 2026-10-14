"""Unprivileged regression tests for the CI-only harness."""
import importlib.util
from pathlib import Path

import pytest


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_stop_assertion_does_not_prevent_unit_removal(tmp_path, monkeypatch):
    lifecycle = load('systemd_lifecycle')
    unit = tmp_path / lifecycle.UNIT
    unit.write_text('unit')
    override = tmp_path / (lifecycle.UNIT + '.d') / 'fixture.conf'
    override.parent.mkdir()
    override.write_text('override')
    calls = []

    def command(*args, **kwargs):
        calls.append(args)
        if 'stop' in args:
            raise AssertionError('stop failed')

    monkeypatch.setattr(lifecycle, 'command', command)
    monkeypatch.setattr(lifecycle, 'property_value', lambda _: 'not-found')
    with pytest.raises(AssertionError, match='stop failed'):
        lifecycle.cleanup_unit(unit)
    assert not unit.exists()
    assert not override.exists()
    assert any('daemon-reload' in args for args in calls)


def test_injected_lifecycle_failure_survives_cleanup_assertion(tmp_path, monkeypatch):
    lifecycle = load('systemd_lifecycle')
    monkeypatch.setattr(lifecycle.sys, 'argv', ['fixture', '--inject-failure'])
    monkeypatch.setattr(lifecycle.sys, 'platform', 'linux')
    monkeypatch.setenv('USER', 'dhci123')
    monkeypatch.setattr(lifecycle.Path, 'home', lambda: tmp_path)
    paths = lifecycle.Paths(tmp_path / 'config with % and $', tmp_path / 'data with % and $',
                            tmp_path / '.config/systemd/user')
    unit = paths.units / lifecycle.UNIT
    properties = {'ActiveState': 'inactive', 'SubState': 'running', 'MainPID': '123',
                  'FragmentPath': str(unit), 'DropInPaths': str(unit) + '.d/fixture.conf',
                  'LoadState': 'not-found'}

    def command(*args, **kwargs):
        if args[-1] == 'install' and not unit.exists():
            paths.units.mkdir(parents=True)
            unit.write_text(lifecycle.unit_text(paths))
            unit.chmod(0o600)
        if args[-1] == 'start':
            properties['ActiveState'] = 'active'
        if 'stop' in args:
            raise AssertionError('secondary cleanup stop assertion')
        return ''

    monkeypatch.setattr(lifecycle, 'command', command)
    monkeypatch.setattr(lifecycle, 'property_value', properties.__getitem__)
    monkeypatch.setattr(lifecycle, 'wait_event', lambda *args: None)
    with pytest.raises(SystemExit) as failure:
        lifecycle.main()
    assert failure.value.code == 73
    assert not unit.exists()
    assert not (paths.units / (lifecycle.UNIT + '.d')).exists()


def test_owned_path_removal_refuses_replacements_and_symlinks(tmp_path):
    owner = load('systemd_ci_owner')
    home = tmp_path / 'home'
    home.mkdir()
    identity = owner.identity(home)
    (home / 'fixture').write_text('owned')
    owner.remove_owned(home, identity)
    assert not home.exists()
    home.mkdir()
    identity = owner.identity(home)
    other = tmp_path / 'other'
    other.mkdir()
    (other / 'keep').write_text('unknown')
    home.rmdir()
    home.symlink_to(other, target_is_directory=True)
    with pytest.raises(RuntimeError, match='ownership'):
        owner.remove_owned(home, identity)
    assert (other / 'keep').exists()
    home.unlink()
    home.mkdir()
    with pytest.raises(RuntimeError, match='ownership'):
        owner.remove_owned(home, None)
    assert home.exists()


def test_orphan_recovery_uses_saved_identity_without_passwd(tmp_path, monkeypatch):
    owner = load('systemd_ci_owner')
    user, uid = 'dhci123', 23456
    home, runtime, directory = (tmp_path / n for n in ('home', 'runtime', 'state'))
    for path in (home, runtime, directory):
        path.mkdir()
    state = {'uid': uid, 'token': 'test', 'home': owner.identity(home),
             'runtime': owner.identity(runtime)}
    owner.save(directory, state)
    monkeypatch.setattr(owner, 'Path', lambda name: {f'/home/{user}': home, f'/run/user/{uid}': runtime}[name])
    monkeypatch.setattr(owner, 'account', lambda _: None)
    monkeypatch.setattr(owner.pwd, 'getpwall', lambda: [])
    commands = []

    def run(*args, **kwargs):
        from types import SimpleNamespace
        commands.append(args)
        return SimpleNamespace(returncode=0, stdout='inactive\n')

    monkeypatch.setattr(owner, 'run', run)
    owner.cleanup(user, directory, state)
    assert not home.exists() and not runtime.exists() and not directory.exists()
    assert not any('userdel' in args for args in commands)


def test_orphan_probe_requires_account_absence_and_both_paths(tmp_path, monkeypatch):
    owner = load('systemd_ci_owner')
    home, runtime = tmp_path / 'home', tmp_path / 'runtime'
    home.mkdir()
    runtime.mkdir()
    state = {'uid': 23456, 'home': owner.identity(home), 'runtime': owner.identity(runtime)}
    monkeypatch.setattr(owner, 'Path', lambda name: home if name.startswith('/home/') else runtime)
    monkeypatch.setattr(owner, 'account', lambda _: None)
    owner.verify_orphan('dhci123', state)
    runtime.rmdir()
    with pytest.raises(FileNotFoundError):
        owner.verify_orphan('dhci123', state)


@pytest.mark.parametrize('existing', ['account', 'group', 'home', 'symlink'])
def test_prepare_never_adopts_preexisting_resources(tmp_path, monkeypatch, existing):
    from types import SimpleNamespace
    owner = load('systemd_ci_owner')
    home = tmp_path / 'dhci123'
    if existing == 'home':
        home.mkdir()
    elif existing == 'symlink':
        home.symlink_to(tmp_path / 'missing')
    monkeypatch.setattr(owner, 'Path', lambda _: tmp_path)
    monkeypatch.setattr(owner, 'account', lambda _: object() if existing == 'account' else None)
    monkeypatch.setattr(owner.grp, 'getgrall', lambda: [SimpleNamespace(gr_name='dhci123')] if existing == 'group' else [])
    monkeypatch.setattr(owner, 'run', lambda *args, **kwargs: pytest.fail('must not run useradd'))
    with pytest.raises(RuntimeError, match='preexisting'):
        owner.prepare('dhci123', tmp_path / 'state')
    assert not (tmp_path / 'state').exists()


@pytest.mark.parametrize('change', ['uid', 'token', 'home', 'reused-uid'])
def test_replaced_account_or_reused_uid_is_not_owned(monkeypatch, change):
    from types import SimpleNamespace
    owner = load('systemd_ci_owner')
    state = {'uid': 23456, 'token': 'owned'}
    entry = SimpleNamespace(pw_uid=23456, pw_gecos='owned', pw_dir='/home/dhci123')
    if change == 'uid':
        entry.pw_uid = 23457
    elif change == 'token':
        entry.pw_gecos = 'other'
    elif change == 'home':
        entry.pw_dir = '/home/other'
    monkeypatch.setattr(owner, 'account', lambda _: entry)
    monkeypatch.setattr(owner.pwd, 'getpwall', lambda: [SimpleNamespace(pw_uid=23456, pw_name='other')]
                        if change == 'reused-uid' else [])
    with pytest.raises(RuntimeError, match='refusing'):
        owner.validate_account('dhci123', state)


def test_privileged_helper_refuses_non_hosted_environment(monkeypatch):
    owner = load('systemd_ci_owner')
    monkeypatch.setattr(owner.sys, 'platform', 'linux')
    monkeypatch.setattr(owner.os, 'geteuid', lambda: 0)
    monkeypatch.setenv('GITHUB_ACTIONS', 'true')
    monkeypatch.setenv('RUNNER_ENVIRONMENT', 'self-hosted')
    with pytest.raises(RuntimeError, match='GitHub-hosted'):
        owner.main()


def test_unknown_path_blocks_all_privileged_cleanup(tmp_path, monkeypatch):
    owner = load('systemd_ci_owner')
    home = tmp_path / 'home'
    home.mkdir()
    state = {'uid': 23456, 'token': 'test', 'home': None, 'runtime': None}
    monkeypatch.setattr(owner, 'Path', lambda name: home if name.startswith('/home/') else tmp_path / 'absent')
    monkeypatch.setattr(owner, 'validate_account', lambda *args: None)
    monkeypatch.setattr(owner, 'run', lambda *args, **kwargs: pytest.fail('privileged operation on unknown path'))
    with pytest.raises(RuntimeError, match='ownership'):
        owner.cleanup('dhci123', tmp_path, state)
    assert home.exists()
