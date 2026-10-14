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
    finally:
        command('systemctl', '--user', 'stop', UNIT)
        if unit.exists():
            unit.unlink()
        override = paths.units / f'{UNIT}.d/fixture.conf'
        override.unlink(missing_ok=True)
        if override.parent.exists():
            override.parent.rmdir()
        command('systemctl', '--user', 'daemon-reload')
        assert property_value('LoadState') == 'not-found'
        print('PASS: service stopped and unit/drop-in removed', flush=True)


if __name__ == '__main__':
    main()
