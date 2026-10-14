"""Stdlib-only entry point for a reviewed, user-local Linux installation.

No remote shell, sudo, automatic upgrades, credential copying or API fallback.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shlex
import shutil
import stat
import subprocess
import sys
import time


class InstallError(RuntimeError):
    pass


def command(args, **kwargs):
    result = subprocess.run([str(a) for a in args], text=True, capture_output=True, **kwargs)
    if result.returncode:
        # Package managers and auth commands may emit secrets from inherited config.
        raise InstallError('Command failed: ' + Path(str(args[0])).name + '; details suppressed. Fix dependencies/network and rerun.')
    return result.stdout.strip()


def preflight(interactive):
    if sys.platform != 'linux':
        raise InstallError('Linux with user systemd required. This installer does not deploy from macOS/Windows.')
    if os.getuid() == 0:
        raise InstallError('Run as a non-root Linux user, without sudo.')
    if sys.version_info < (3, 9):
        raise InstallError('Python 3.9+ required.')
    for name in ('git', 'node', 'npm', 'systemctl'):
        if not shutil.which(name):
            raise InstallError(f'Missing dependency: {name}. Install using your distribution package manager; no sudo is run automatically.')
    try:
        import ensurepip  # noqa: F401
        import venv  # noqa: F401
    except ImportError:
        raise InstallError('Python venv/ensurepip missing. Debian/Ubuntu: ask the administrator to install python3-venv.') from None
    if int(command(['node', '-p', 'process.versions.node.split(".")[0]'])) < 18:
        raise InstallError('Node.js 18+ required (CI uses 22).')
    if interactive:
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise InstallError('Interactive terminal required for hidden token input and OAuth. Use --prepare-only for software-only preparation.')
        command(['systemctl', '--user', 'show-environment'], timeout=15)


def safe_path(path):
    path = Path(path).absolute()
    for part in (path, *path.parents):
        if part.is_symlink():
            raise InstallError('Symlinked installation/configuration path refused.')
    if path.exists() and path.stat().st_uid != os.getuid():
        raise InstallError('Installation path must belong to the current user.')
    return path


def write_new(path, text, mode=0o600):
    safe_path(path)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, 'w') as stream:
        stream.write(text)


def prepare_checkout(source, root):
    source, root = Path(source).absolute(), safe_path(root)
    revision = command(['git', '-C', source, 'rev-parse', 'HEAD'])
    if command(['git', '-C', source, 'status', '--porcelain', '--untracked-files=no']):
        raise InstallError('Source checkout changed; commit/review it before installation.')
    marker = root/'installer.json'
    if not root.exists():
        root.mkdir(parents=True, mode=0o700)
        write_new(marker, json.dumps({'revision': revision}) + '\n')
    elif not marker.is_file() or marker.is_symlink():
        raise InstallError('Unowned installation directory; refusing adoption or overwrite.')
    if root.stat().st_mode & 0o077 or marker.stat().st_mode & 0o077:
        raise InstallError('Installation directory/marker must be owner-private.')
    if json.loads(marker.read_text()) != {'revision': revision}:
        raise InstallError('Different pinned revision already installed; no automatic upgrades. Rerun the installed checkout or review a manual migration.')
    checkout = safe_path(root/'app')
    if not checkout.exists():
        command(['git', 'clone', '--no-hardlinks', '--no-checkout', source, checkout])
        command(['git', '-C', checkout, 'checkout', '--detach', revision])
    if command(['git', '-C', checkout, 'rev-parse', 'HEAD']) != revision or command(
            ['git', '-C', checkout, 'status', '--porcelain', '--untracked-files=no']):
        raise InstallError('Installed checkout changed or interrupted; preserved for manual inspection.')
    return checkout


def default_paths():
    from .manage import Paths
    config = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home()/'.config'))).absolute()
    data = Path(os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share'))).absolute()
    return Paths(config/'discord-helper', data/'discord-helper', config/'systemd/user')


def ask(message):
    return input(message).strip()


def oauth_ready(paths):
    from .manage import private_dir
    executable = paths.data/'tools/node_modules/.bin/codex'
    home = private_dir(paths.data/'codex')
    login_home = private_dir(paths.data/'login-home')
    auth = safe_path(home/'auth.json')
    if not auth.is_file():
        return False
    if auth.stat().st_mode & 0o077:
        raise InstallError('OAuth auth.json must be private (mode 600); not changed automatically.')
    if (home/'config.toml').exists() or (home/'config.toml').is_symlink():
        raise InstallError('App-isolated Codex config.toml is unsupported; inspect it manually.')
    env = {'HOME': str(login_home), 'CODEX_HOME': str(home), 'PATH': os.environ.get('PATH', os.defpath)}
    result = subprocess.run([str(executable), '-c', 'cli_auth_credentials_store="file"',
                             '-c', 'forced_login_method="chatgpt"', 'login', 'status'],
                            env=env, cwd=login_home, text=True, capture_output=True, timeout=30)
    return result.returncode == 0 and 'Logged in using ChatGPT' in (result.stdout + result.stderr)


def offline_check(paths):
    """Check fresh schema/provider without opening a running service's database."""
    from tempfile import TemporaryDirectory
    from . import manage as m
    provider = m.build_provider('codex-oauth', data=paths.data)
    m.private_dir(paths.data)
    with TemporaryDirectory(prefix='install-check-', dir=paths.data) as directory:
        scratch = m.Paths(paths.config, Path(directory), paths.units)
        if m.run(scratch, check=True, provider_name='codex-oauth', codex_executable=provider.executable):
            raise InstallError('Offline configuration check failed; service NOT started.')


def service_readback():
    # A process that survives this window is NOT proof of Discord readiness.
    before = command(['systemctl', '--user', 'show', 'discord-helper.service', '--property=MainPID', '--value'])
    time.sleep(3)
    command(['systemctl', '--user', 'is-active', '--quiet', 'discord-helper.service'])
    after = command(['systemctl', '--user', 'show', 'discord-helper.service', '--property=MainPID', '--value'])
    if before == '0' or before != after:
        raise InstallError('Service exited/restarted during startup; inspect status locally and rerun.')


def finish(paths):
    from . import manage as m
    for directory in (paths.config, paths.data, paths.units):
        safe_path(directory)
    m.private_dir(paths.config)
    runtime = paths.config/'runtime.json'
    if not runtime.exists() and not runtime.is_symlink():
        guild = ask('Test Discord server (guild) ID [required; no global default]: ')
        if not guild.isascii() or not guild.isdigit() or not 0 < int(guild) < 2**64:
            raise InstallError('Enter a positive Discord server ID, not its name; no global sync selected.')
        m.secure_create(runtime, json.dumps({'provider': 'codex-oauth', 'sync_guild': int(guild)}) + '\n')
    config = m.runtime_config(paths)
    if config['provider'] != 'codex-oauth' or config['sync_guild'] is None:
        raise InstallError('Existing runtime.json preserved; installer requires codex-oauth and a test guild. Review settings manually.')
    # Never accept inherited token values during interactive installation.
    os.environ.pop('DISCORD_BOT_TOKEN', None)
    import warnings
    import getpass
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        m.setup(paths)
    m.load_token(paths)
    if not oauth_ready(paths):
        if m.codex_login(paths) != 0 or not oauth_ready(paths):
            raise InstallError('OAuth not verified; service NOT started. Enable device login if required and rerun, or use codex-login --browser locally.')
    offline_check(paths)
    m.install(paths)
    if m.lifecycle(paths, 'start') or m.lifecycle(paths, 'status'):
        raise InstallError('Service start/status failed. Saved configuration preserved; rerun after diagnosis.')
    service_readback()
    print('Software installed; ChatGPT login status verified; service active at readback.')
    print('NOT YET VERIFIED: Discord login/invite, command sync, live answer and persistence. Test /channel enabled:true then /ask in the selected guild.')
    print('Service is NOT enabled at boot; logout may stop the user manager. See docs/INSTALL_KO.md for explicit opt-in persistence.')


def installed_main():
    try:
        finish(default_paths())
        return 0
    except (KeyboardInterrupt, EOFError):
        print('Cancelled; saved state preserved, readiness not confirmed.', file=sys.stderr)
        return 130
    except Exception as exc:
        from .manage import ManagementError
        print(str(exc) if isinstance(exc, (InstallError, ManagementError)) else 'Setup failed; sensitive details suppressed. Rerun to resume.', file=sys.stderr)
        return 2


def prepare_software(checkout, root):
    data = safe_path(Path(os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share'))).absolute()/'discord-helper')
    tools = safe_path(data/'tools')
    ownership = safe_path(root/'tools-owner.json')
    config = safe_path(Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home()/'.config'))).absolute()/'discord-helper')
    expected = json.dumps({'tools': str(tools), 'config': str(config)}) + '\n'
    if ownership.exists():
        if ownership.read_text() != expected:
            raise InstallError('Application tools path changed; original settings preserved. Restore XDG_DATA_HOME.')
    else:
        if tools.exists():
            raise InstallError('Unowned application tools directory; refusing npm overwrite. Review/migrate it manually.')
        write_new(ownership, expected)
    python = root/'venv/bin/python'
    venv_dir = safe_path(root/'venv')
    if not venv_dir.exists():
        command([sys.executable, '-m', 'venv', venv_dir])
    if not python.is_file():
        raise InstallError('Incomplete venv preserved; inspect installation directory before retrying.')
    complete = safe_path(root/'software-ready')
    if not complete.exists():
        command([python, '-I', '-m', 'pip', 'install', str(checkout)], cwd=root)
        command([python, '-I', '-m', 'helperbot.manage', 'install-codex'], cwd=root)
        command([python, '-I', '-m', 'pip', 'check'], cwd=root)
        write_new(complete, 'software only; not authentication or service readiness\n')
    command([python, '-I', '-m', 'pip', 'check'], cwd=root)
    if command([tools/'node_modules/.bin/codex', '--version'], cwd=root) != 'codex-cli 0.162.1':
        raise InstallError('Application Codex version differs from pinned 0.162.1; not overwritten.')
    # Force the real selected provider's native-binary discovery; no fake auth.
    command([python, '-I', '-c', 'from helperbot.bootstrap import offline_check, default_paths; offline_check(default_paths())'], cwd=root)
    return python


def main(argv=None):
    parser = argparse.ArgumentParser(description='User-local Linux installer; no sudo, no API-key fallback.')
    parser.add_argument('--prepare-only', action='store_true', help='Install pinned software only; no secrets, login or service start; NOT ready')
    args = parser.parse_args(argv)
    os.umask(0o077)
    try:
        preflight(not args.prepare_only)
        root = safe_path(Path.home()/'.local/share/discord-helper-install')
        source = Path(__file__).resolve().parents[1]
        checkout = prepare_checkout(source, root)
        lock = os.open(root/'install.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            python = prepare_software(checkout, root)
            wrapper = root/'discord-helper'
            settings = json.loads((root/'tools-owner.json').read_text())
            config = Path(settings['config'])
            data = Path(settings['tools']).parent
            cli = [str(python), '-I', '-m', 'helperbot.manage', '--config-dir', str(config),
                   '--data-dir', str(data), '--unit-dir', str(config.parent/'systemd/user')]
            text = '#!/bin/sh\nexec ' + ' '.join(shlex.quote(arg) for arg in cli) + ' "$@"\n'
            if not wrapper.exists():
                write_new(wrapper, text, 0o700)
            elif wrapper.is_symlink() or wrapper.read_text() != text:
                raise InstallError('Existing launcher differs; preserved, not overwritten.')
            print('Management command: ' + str(wrapper), flush=True)
            if args.prepare_only:
                print('PREPARED ONLY: no Discord token, OAuth login or service start performed. NOT READY. Rerun bash install.sh interactively.')
                return 0
            result = subprocess.run([str(python), '-I', '-c', 'from helperbot.bootstrap import installed_main; raise SystemExit(installed_main())'], cwd=root)
            return result.returncode
        finally:
            os.close(lock)
    except (KeyboardInterrupt, EOFError):
        print('Cancelled; saved state preserved. Rerun to resume.', file=sys.stderr)
        return 130
    except Exception as exc:
        print(str(exc) if isinstance(exc, InstallError) else 'Installation failed; existing state preserved, sensitive details suppressed. Inspect dependencies/paths and rerun.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
