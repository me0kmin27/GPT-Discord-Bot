"""Privileged ownership bookkeeping for disposable hosted CI, NOT an operator tool.

State is root-private, paths are derived, and unknown/replaced paths are refused.
An interruption before a path identity is recorded may leave it for VM disposal.
"""
import grp
import json
import os
from pathlib import Path
import pwd
import re
import secrets
import shutil
import stat
import subprocess
import sys


def identity(path):
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode):
        raise RuntimeError('directory ownership cannot be established')
    return [info.st_dev, info.st_ino, info.st_uid]


def remove_owned(path, expected):
    if not os.path.lexists(path):
        return
    if expected is None or identity(path) != expected or path.is_mount():
        raise RuntimeError(f'refusing unknown/replaced ownership: {path}')
    # Linux fd-based rmtree does not follow nested symlinks.
    if not shutil.rmtree.avoids_symlink_attacks:
        raise RuntimeError('safe rmtree unavailable')
    shutil.rmtree(path)


def account(name):
    try:
        return pwd.getpwnam(name)
    except KeyError:
        return None


def run(*args, check=True):
    return subprocess.run(args, check=check, text=True, capture_output=True, timeout=45)


def save(directory, state):
    temporary = directory / 'next.json'
    temporary.write_text(json.dumps(state))
    temporary.replace(directory / 'state.json')


def prepare(user, directory):
    home = Path('/home') / user
    if account(user) or any(g.gr_name == user for g in grp.getgrall()) or os.path.lexists(home):
        raise RuntimeError('refusing preexisting account/group/home')
    uid = next(n for n in range(20000, 60000)
               if n not in {p.pw_uid for p in pwd.getpwall()}
               and not os.path.lexists(f'/run/user/{n}'))
    directory.mkdir(mode=0o700)  # exclusive: never adopt an existing state directory
    state = {'uid': uid, 'token': secrets.token_hex(16), 'home': None, 'runtime': None}
    save(directory, state)  # intent precedes useradd; closes account/marker gap
    run('useradd', '--no-create-home', '--user-group', '--uid', str(uid),
        '--home-dir', str(home), '--comment', state['token'], '--shell', '/bin/bash', user)
    home.mkdir(mode=0o700)
    state['home'] = identity(home)
    save(directory, state)
    os.chown(home, uid, pwd.getpwnam(user).pw_gid)
    state['home'] = identity(home)
    save(directory, state)
    print(uid, flush=True)


def validate_account(user, state):
    entry = account(user)
    if entry and (entry.pw_uid != state['uid'] or entry.pw_gecos != state['token']
                  or entry.pw_dir != f'/home/{user}'):
        raise RuntimeError('refusing replaced account')
    if any(p.pw_uid == state['uid'] and p.pw_name != user for p in pwd.getpwall()):
        raise RuntimeError('refusing reused UID')
    return entry


def cleanup(user, directory, state, orphan=False):
    entry = validate_account(user, state)
    uid = state['uid']
    home, runtime = Path(f'/home/{user}'), Path(f'/run/user/{uid}')
    # Validate before privileged stop/delete; missing paths are already clean.
    for path, expected in ((home, state['home']), (runtime, state['runtime'])):
        if os.path.lexists(path) and (expected is None or identity(path) != expected):
            raise RuntimeError(f'refusing unknown/replaced ownership: {path}')
    errors = []
    for unit in (f'user@{uid}.service', f'user-runtime-dir@{uid}.service'):
        result = run('systemctl', 'stop', unit, check=False)
        if result.returncode:
            errors.append(f'stop failed: {unit}')
    if entry:
        run('userdel', user)  # no --remove: only independently owned paths below
    if orphan:
        # Test-only interruption after passwd removal, before owned-path removal.
        # Runtime service normally removes its directory; recreate a tracked orphan.
        if not runtime.exists():
            runtime.mkdir(mode=0o700)
            os.chown(runtime, uid, 0)
            state['runtime'] = identity(runtime)
            save(directory, state)
        print('INJECT: account removed; owned home/runtime retained', flush=True)
        return
    for path, expected in ((home, state['home']), (runtime, state['runtime'])):
        try:
            remove_owned(path, expected)
        except Exception as error:
            errors.append(str(error))
    manager = run('systemctl', 'show', f'user@{uid}.service', '--property=ActiveState', '--value').stdout.strip()
    if manager != 'inactive' or account(user) or os.path.lexists(home) or os.path.lexists(runtime):
        errors.append('cleanup readback incomplete')
    if errors:
        raise RuntimeError('; '.join(errors))
    (directory / 'state.json').unlink()
    directory.rmdir()
    print('PASS: owned manager/account/home/runtime/state removed', flush=True)


def verify_orphan(user, state):
    if account(user) or identity(Path(f'/home/{user}')) != state['home'] or identity(
            Path(f'/run/user/{state["uid"]}')) != state['runtime']:
        raise RuntimeError('injected orphan precondition not established')
    print('PASS: passwd absent; owned home AND runtime orphans verified', flush=True)


def main():
    if not (sys.platform == 'linux' and os.geteuid() == 0
            and os.environ.get('GITHUB_ACTIONS') == 'true'
            and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'):
        raise RuntimeError('disposable GitHub-hosted Linux root helper only')
    user = 'dhci' + os.environ['GITHUB_RUN_ID'] + os.environ['GITHUB_RUN_ATTEMPT']
    if not re.fullmatch(r'dhci[0-9]{1,28}', user):
        raise RuntimeError('invalid CI account')
    directory = Path('/run') / (user + '.owned')
    action = sys.argv[1]
    if action == 'prepare':
        prepare(user, directory)
        return
    if not os.path.lexists(directory):
        if action == 'cleanup':
            return
        raise RuntimeError('missing ownership state')
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o700:
        raise RuntimeError('invalid ownership state directory')
    state = json.loads((directory / 'state.json').read_text())
    if not isinstance(state['uid'], int) or not 20000 <= state['uid'] < 60000:
        raise RuntimeError('invalid reserved UID')
    validate_account(user, state)
    if action == 'runtime':
        state['runtime'] = identity(Path(f'/run/user/{state["uid"]}'))
        if state['runtime'][2] != state['uid']:
            raise RuntimeError('unexpected runtime owner')
        save(directory, state)
    elif action == 'verify-orphan':
        verify_orphan(user, state)
    elif action in ('cleanup', 'inject-orphan'):
        cleanup(user, directory, state, orphan=action == 'inject-orphan')
    else:
        raise RuntimeError('unknown action')


if __name__ == '__main__':
    main()
