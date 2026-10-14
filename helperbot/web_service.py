"""Optional fixed user service; never enabled or started by installation."""
import subprocess
import sys
from .manage import ManagementError, MARKER, private_dir, require_systemd, secure_create, unit_quote

WEB_UNIT = 'discord-helper-web.service'


def gui_service(paths, action, *, port=8765, runner=subprocess.run):
    if action not in ('install', 'start', 'stop', 'status'):
        raise ManagementError('Unsupported GUI service action.')
    require_systemd()
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ManagementError('GUI port must be 1024–65535.')
    if action == 'install':
        private_dir(paths.units)
        command = ' '.join(unit_quote(arg, command=True) for arg in [
            sys.executable, '-m', 'helperbot.manage', '--config-dir', paths.config,
            '--data-dir', paths.data, '--unit-dir', paths.units])
        command += ' gui run --port '+str(port)
        text = MARKER + ('[Unit]\nDescription=Private Discord Helper Web GUI\n\n'
                         '[Service]\nType=simple\nExecStart='+command+'\n'
                         'UMask=0077\nNoNewPrivileges=true\nRestart=on-failure\nRestartSec=10\n'
                         'TimeoutStopSec=15\n\n[Install]\nWantedBy=default.target\n')
        target = paths.units/WEB_UNIT
        if target.is_symlink():
            raise ManagementError('Symlinked GUI unit refused.')
        if target.exists():
            if target.read_text() != text:
                raise ManagementError('Different GUI unit preserved. Review locally before replacing.')
        elif not secure_create(target, text):
            raise ManagementError('GUI unit appeared concurrently.')
        if target.read_text() != text:
            raise ManagementError('GUI unit verification failed.')
        args = ['systemctl', '--user', 'daemon-reload']
    else:
        args = ['systemctl', '--user', action, WEB_UNIT]
        if action == 'status':
            args += ['--no-pager']
    try:
        result = runner(args, capture_output=True, text=True, timeout=20)
        if result.returncode:
            return result.returncode
        if action in ('start', 'stop'):
            state = runner(['systemctl', '--user', 'is-active', '--quiet', WEB_UNIT],
                           capture_output=True, text=True, timeout=10)
            return (0 if state.returncode == 3 else 1) if action == 'stop' else state.returncode
        print('GUI unit installed; NOT started or enabled.' if action == 'install' else 'GUI service status command succeeded (raw logs suppressed).')
        return 0
    except (OSError, subprocess.TimeoutExpired):
        raise ManagementError('GUI user service unavailable; no raw output shown.') from None
