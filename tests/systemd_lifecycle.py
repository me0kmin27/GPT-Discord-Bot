"""Explicit CI integration entry point; real systemctl, disposable user only."""
import os
from pathlib import Path
import subprocess
import sys
import time

from helperbot.manage import Paths, UNIT, unit_quote, unit_text


def command(*args, expected=0):
    result = subprocess.run(args, text=True, capture_output=True, timeout=45)
    print(f'$ {" ".join(map(str, args))}\n{result.stdout}{result.stderr}', flush=True)
    assert result.returncode == expected, (args, result.returncode, expected)
    return result.stdout.strip()


def property_value(name):
    return command('systemctl', '--user', 'show', UNIT, f'--property={name}', '--value')


def wait_event(log, event, pid):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if log.exists() and f'{event} {pid}' in log.read_text().splitlines():
            print(f'fixture acknowledgement: {event} {pid}', flush=True)
            return
        time.sleep(0.1)
    raise AssertionError(f'fixture did not acknowledge {event} {pid}')


def cleanup_unit(unit):
    errors = []
    override = unit.parent / f'{UNIT}.d/fixture.conf'
    actions = [
        lambda: command('systemctl', '--user', 'stop', UNIT,
                        expected=99 if sys.argv[1:] == ['--inject-failure'] else 0),
        lambda: unit.unlink(missing_ok=True),
        lambda: override.unlink(missing_ok=True),
        lambda: override.parent.rmdir() if override.parent.exists() else None,
        lambda: command('systemctl', '--user', 'daemon-reload'),
    ]
    for action in actions:
        try:
            action()
        except Exception as error:
            errors.append(error)
            print(f'cleanup error: {error}', flush=True)
    try:
        assert property_value('LoadState') == 'not-found'
        assert not unit.exists() and not override.exists()
        print('PASS: unit/drop-in removed; LoadState=not-found', flush=True)
    except Exception as error:
        errors.append(error)
    if errors:
        raise errors[0]


def main():
    assert sys.platform == 'linux' and os.getuid() != 0
    assert os.environ['USER'].startswith('dhci')
    home = Path.home()
    paths = Paths(home / 'config with % and $', home / 'data with % and $',
                  home / '.config/systemd/user')
    cli = [str(Path(sys.executable).parent / 'discord-helper'),
           '--config-dir', str(paths.config), '--data-dir', str(paths.data),
           '--unit-dir', str(paths.units)]
    unit = paths.units / UNIT
    log = paths.data / 'fixture-events'
    try:
        command(*cli, 'install')
        original = unit.read_bytes()
        original_stat = unit.stat()
        assert original.decode() == unit_text(paths)
        command(*cli, 'install')
        assert unit.read_bytes() == original
        assert unit.stat().st_ino == original_stat.st_ino
        assert unit.stat().st_mtime_ns == original_stat.st_mtime_ns
        assert unit.stat().st_mode & 0o777 == 0o600
        assert property_value('ActiveState') == 'inactive'
        command('systemctl', '--user', 'is-enabled', UNIT, expected=1)
        command(*cli, 'status', expected=3)
        # Keep the actual installed unit unchanged. Only this disposable user's
        # test drop-in replaces the networked bot executable, never systemctl.
        dropin = paths.units / f'{UNIT}.d'
        dropin.mkdir()
        fixture = Path(__file__).with_name('systemd_fixture.py').resolve()
        argv = ' '.join(unit_quote(x, command=True) for x in (sys.executable, fixture, log))
        (dropin / 'fixture.conf').write_text(
            '[Service]\nExecStart=\nExecStart=' + argv + '\nRestrictAddressFamilies=AF_UNIX\n')
        command('systemctl', '--user', 'daemon-reload')
        assert property_value('FragmentPath') == str(unit)
        assert str(dropin / 'fixture.conf') in property_value('DropInPaths')
        command(*cli, 'start')
        assert property_value('ActiveState') == 'active'
        assert property_value('SubState') == 'running'
        first = int(property_value('MainPID'))
        assert first > 0
        wait_event(log, 'start', first)
        if sys.argv[1:] == ['--inject-failure']:
            print('INJECT: original lifecycle exit 73 after real fixture start', flush=True)
            raise SystemExit(73)
        command(*cli, 'status')
        command(*cli, 'restart')
        second = int(property_value('MainPID'))
        assert second > 0 and second != first
        wait_event(log, 'stop', first)
        wait_event(log, 'start', second)
        assert property_value('ActiveState') == 'active'
        command(*cli, 'status')
        command(*cli, 'stop')
        wait_event(log, 'stop', second)
        assert property_value('ActiveState') == 'inactive'
        assert property_value('MainPID') == '0'
        assert property_value('Result') == 'success'
        command(*cli, 'status', expected=3)
        command(*cli, 'stop')
        assert unit.read_bytes() == original
        assert not (paths.config / 'credentials.json').exists()
        assert not (paths.data / 'state.db').exists()
        print('PASS: real user-systemd fixture lifecycle; NOT live bot readiness', flush=True)
        # Exercise installer orchestration with explicit offline human/network
        # fixtures, but REAL setup storage, provider discovery, unit and systemctl.
        from unittest.mock import patch
        from helperbot import bootstrap, manage
        native = paths.data/'tools/node_modules/@openai/codex-fixture/vendor/fixture/bin/codex'
        native.parent.mkdir(parents=True)
        native.write_text('CI discovery fixture only; never executed')
        with patch.object(bootstrap, 'ask', return_value='123456789'), patch.object(
                manage.getpass, 'getpass', return_value='CI-FIXTURE-NOT-A-TOKEN'), patch.object(
                bootstrap, 'oauth_ready', return_value=True):
            bootstrap.finish(paths)
            saved = (paths.config/'credentials.json').read_bytes()
            settings = (paths.config/'runtime.json').read_bytes()
            bootstrap.finish(paths)
            assert (paths.config/'credentials.json').read_bytes() == saved
            assert (paths.config/'runtime.json').read_bytes() == settings
        assert manage.runtime_config(paths) == {'provider': 'codex-oauth', 'sync_guild': 123456789}
        assert (paths.data/'state.db').is_file()
        command(*cli, 'stop')
        print('PASS: installer finish/rerun + real systemd; token/OAuth/Discord are OFFLINE FIXTURES, NOT live readiness', flush=True)
    finally:
        original_error = sys.exc_info()[0] is not None
        try:
            cleanup_unit(unit)
        except Exception:
            if not original_error:
                raise
            print('cleanup failed; preserving original lifecycle exception', flush=True)


if __name__ == '__main__':
    main()
