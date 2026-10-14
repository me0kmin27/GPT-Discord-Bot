"""Local operator tooling; Codex OAuth requires explicit runtime selection."""
from dataclasses import dataclass
from pathlib import Path
import getpass
import json
import os
import stat
import platform
import shutil
import subprocess
import sys
import argparse
import asyncio
import fcntl
from contextlib import contextmanager
from .core import Store
from .discord_app import create_client
from .provider import build_provider
from .diagnostics import StartupFailure, diagnostic


class ManagementError(RuntimeError):
    pass


@dataclass(frozen=True)
class Paths:
    config: Path
    data: Path
    units: Path


UNIT = 'discord-helper.service'
MARKER = '# Managed by discord-helper; no credentials in this file.\n'


def unit_quote(value, *, command=False):
    value = str(value)
    if any(ord(c) < 32 for c in value):
        raise ManagementError('Control characters are not allowed in service paths')
    value = value.replace('%', '%%')
    if command:
        value = value.replace('$', '$$')
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def unit_text(paths):
    command = ' '.join(unit_quote(arg, command=True) for arg in [
        sys.executable, '-m', 'helperbot.manage', '--config-dir', paths.config,
        '--data-dir', paths.data, '--unit-dir', paths.units]) + ' run'
    return MARKER + (
        '[Unit]\nDescription=Opt-in Discord knowledge helper\n'
        'After=network-online.target\n\n[Service]\nType=simple\n'
        f'ExecStart={command}\n'
        'UMask=0077\nNoNewPrivileges=true\nRestart=on-failure\nRestartSec=10\n'
        'TimeoutStopSec=30\n\n[Install]\nWantedBy=default.target\n')


def require_systemd():
    if platform.system() != 'Linux' or not shutil.which('systemctl'):
        raise ManagementError('Linux user systemd unavailable; use discord-helper run in foreground')
    if os.getuid() == 0:
        raise ManagementError('Use a non-root service account; no sudo/root installation')


def install(paths, *, runner=subprocess.run):
    require_systemd()
    private_dir(paths.config)
    private_dir(paths.data)
    private_dir(paths.units)
    target = paths.units / UNIT
    content = unit_text(paths)
    if target.is_symlink():
        raise ManagementError('Refusing symlinked service unit')
    if target.exists():
        if target.read_text() != content:
            raise ManagementError('Existing service differs; stop and review/remove it explicitly before reinstalling')
    elif not secure_create(target, content):
        raise ManagementError('Service appeared concurrently; not overwritten')
    if target.read_text() != content:
        raise ManagementError('Service write verification failed')
    result = runner(['systemctl', '--user', 'daemon-reload'])
    if result.returncode:
        raise ManagementError('Unit saved but user systemd is unavailable; use a user session or foreground run')
    print('User service installed; not started or enabled. Credentials preserved.')


def lifecycle(paths, action, *, follow=False, runner=subprocess.run):
    require_systemd()
    if action == 'logs':
        if not shutil.which('journalctl'):
            raise ManagementError('journalctl is unavailable')
        args = ['journalctl', '--user', '-u', UNIT, '-n', '100', '--no-pager']
        if follow:
            args.append('--follow')
    elif action in ('start', 'stop', 'restart', 'status'):
        args = ['systemctl', '--user', action, UNIT]
        if action == 'status':
            args.append('--no-pager')
    else:
        raise ManagementError('Unknown lifecycle action')
    result = runner(args)
    if result.returncode:
        return result.returncode
    if action in ('start', 'stop', 'restart'):
        state = runner(['systemctl', '--user', 'is-active', '--quiet', UNIT])
        if action == 'stop':
            return 0 if state.returncode == 3 else 1
        return state.returncode
    return 0


def install_codex(paths, *, runner=subprocess.run):
    npm = shutil.which('npm')
    if not npm:
        raise ManagementError('Install Node.js/npm first, or install official Codex CLI separately')
    private_dir(paths.data)
    prefix = private_dir(paths.data / 'tools')
    from .codex_transport import CODEX_VERSION
    return runner([npm, 'install', '--prefix', str(prefix), '--no-audit', '--no-fund', '@openai/codex@' + CODEX_VERSION]).returncode


def codex_login(paths, *, browser=False, runner=subprocess.run):
    private_dir(paths.data)
    home = private_dir(paths.data / 'codex')
    local = paths.data / 'tools' / 'node_modules' / '.bin' / 'codex'
    executable = str(local) if local.is_file() else shutil.which('codex')
    if not executable:
        raise ManagementError('Codex CLI not installed; run discord-helper install-codex first')
    login_home = private_dir(paths.data / 'login-home')
    env = {key: os.environ[key] for key in ('PATH', 'LANG', 'TERM') if key in os.environ}
    env['HOME'] = str(login_home)
    env['CODEX_HOME'] = str(home)
    command = [executable, '-c', 'cli_auth_credentials_store="file"',
               '-c', 'forced_login_method="chatgpt"', 'login']
    if not browser:
        command.append('--device-auth')
    print('Official Codex login in isolated app home. Provider selection is controlled by runtime.json / run --provider.')
    old_mask = os.umask(0o077)
    try:
        return runner(command, env=env, cwd=login_home).returncode
    finally:
        os.umask(old_mask)


def private_dir(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ManagementError("Refusing symlinked runtime/config path")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.stat().st_uid != os.getuid():
        raise ManagementError("Runtime directory must belong to current user")
    path.chmod(0o700)
    return path


def secure_create(path, content):
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(fd, 'w') as out:
        out.write(content)
    return True


def setup(paths, token=None):
    private_dir(paths.config)
    private_dir(paths.data)
    target = paths.config / 'credentials.json'
    if target.is_symlink():
        raise ManagementError("Refusing symlinked credentials")
    if target.exists():
        print("Existing credentials preserved; setup made no credential changes.")
        return
    if token is None:
        token = os.environ.get('DISCORD_BOT_TOKEN')
    if token is None:
        token = getpass.getpass('Discord bot token (local hidden input): ')
    if not token or any(c.isspace() for c in token) or len(token) > 512:
        raise ManagementError("Invalid token format (content not logged)")
    if not secure_create(target, json.dumps({'DISCORD_BOT_TOKEN': token}) + '\n'):
        raise ManagementError("Credentials appeared concurrently; not overwritten")
    print("Credentials saved privately; provider selection is unchanged.")


def load_token(paths):
    target = paths.config / 'credentials.json'
    if any(p.is_symlink() for p in (target, *target.parents)):
        raise ManagementError("Refusing symlinked credentials path")
    try:
        fd = os.open(str(target), os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd) as src:
            st = os.fstat(src.fileno())
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077:
                raise ManagementError("Credentials require current owner and mode 600")
            data = json.load(src)
        token = data['DISCORD_BOT_TOKEN']
        if not isinstance(token, str) or not token or any(c.isspace() for c in token) or len(token) > 512:
            raise ValueError()
        return token
    except (OSError, ValueError, KeyError, TypeError):
        raise ManagementError("Credentials unavailable/invalid; run discord-helper setup") from None


@contextmanager
def runtime_lock(paths):
    private_dir(paths.data)
    fd = os.open(str(paths.data / 'runtime.lock'), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ManagementError('Another helper instance is already using this data directory') from None
        yield
    finally:
        os.close(fd)


def runtime_config(paths):
    """A private, strictly validated operator selection, not credential discovery."""
    target = paths.config / 'runtime.json'
    if any(p.is_symlink() for p in (target, *target.parents)):
        raise ManagementError('Refusing symlinked runtime configuration')
    if not target.exists():
        return {'provider': 'disabled-codex', 'sync_guild': None}
    try:
        with target.open() as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise ValueError()
            config = json.load(stream)
        if set(config) != {'provider', 'sync_guild'} or config['provider'] not in ('disabled-codex', 'codex-oauth'):
            raise ValueError()
        guild = config['sync_guild']
        if guild is not None and (type(guild) is not int or not 0 < guild < 2**64):
            raise ValueError()
        return config
    except (OSError, ValueError, TypeError):
        raise ManagementError('Invalid runtime.json: require private provider and positive sync_guild (null means global)') from None


def run(paths, *, check=False, sync_guild=None, provider_name=None, codex_executable=None):
    os.umask(0o077)
    config = runtime_config(paths)
    provider_name = provider_name if provider_name is not None else config['provider']
    sync_guild = sync_guild if sync_guild is not None else config['sync_guild']
    try:
        provider = build_provider(provider_name, data=paths.data, executable=codex_executable)
    except ValueError as exc:
        raise ManagementError(str(exc)) from None
    token = None if check else (os.environ.get('DISCORD_BOT_TOKEN') or load_token(paths))
    with runtime_lock(paths):
        store = Store(paths.data / 'state.db')
        try:
            client = create_client(store, sync_guild=sync_guild, provider=provider)
            if check:
                print(f'Offline check OK: {len(client.tree.get_commands())} commands; provider={provider_name}; no network/login')
                asyncio.run(client.close())
            else:
                client.run(token, log_handler=None)
        finally:
            store.close()
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog='discord-helper', description='Discord helper; local Codex OAuth requires explicit selection')
    config_home = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config')))
    data_home = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local' / 'share')))
    parser.add_argument('--config-dir', type=Path, default=config_home / 'discord-helper')
    parser.add_argument('--data-dir', type=Path, default=data_home / 'discord-helper')
    parser.add_argument('--unit-dir', type=Path, default=config_home / 'systemd' / 'user')
    subs = parser.add_subparsers(dest='command', required=True)
    for name in ('install', 'setup', 'install-codex', 'doctor', 'start', 'stop', 'restart', 'status'):
        subs.add_parser(name)
    subs.add_parser('codex-login').add_argument('--browser', action='store_true')
    subs.add_parser('logs').add_argument('--follow', action='store_true')
    foreground = subs.add_parser('run')
    foreground.add_argument('--check', action='store_true')
    foreground.add_argument('--sync-guild', type=int)
    foreground.add_argument('--provider', choices=['disabled-codex', 'codex-oauth'], default=None)
    foreground.add_argument('--codex-executable', type=Path, help='Absolute pinned official native binary; default app-local install')
    args = parser.parse_args(argv)
    paths = Paths(args.config_dir.absolute(), args.data_dir.absolute(), args.unit_dir.absolute())
    try:
        if args.command == 'setup':
            setup(paths)
        elif args.command == 'install':
            install(paths)
        elif args.command == 'install-codex':
            return install_codex(paths)
        elif args.command == 'codex-login':
            return codex_login(paths, browser=args.browser)
        elif args.command == 'run':
            return run(paths, check=args.check, sync_guild=args.sync_guild,
                       provider_name=args.provider, codex_executable=args.codex_executable)
        elif args.command == 'doctor':
            print(f'platform={platform.system()} python={platform.python_version()}')
            config = runtime_config(paths)
            print(f'provider={config["provider"]} sync_guild={config["sync_guild"]}')
            print(f'credentials_present={(paths.config / "credentials.json").is_file()}')
            print(f'systemctl_available={bool(shutil.which("systemctl"))}')
            print(f'codex_available={bool(shutil.which("codex")) or (paths.data / "tools/node_modules/.bin/codex").is_file()}')
            print('Use run --check for an offline schema/command check; doctor does not inspect auth contents.')
        else:
            return lifecycle(paths, args.command, follow=getattr(args, 'follow', False))
        return 0
    except ManagementError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (KeyboardInterrupt, EOFError):
        print('Cancelled; no credentials printed.', file=sys.stderr)
        return 130
    except StartupFailure as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        # Third-party errors may contain secrets; allowlisted metadata only.
        print(diagnostic('operation', exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
