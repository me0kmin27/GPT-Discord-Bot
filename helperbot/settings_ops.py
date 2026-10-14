"""Shared local settings operations. No access to credentials, OAuth or cases."""
from contextlib import contextmanager
import copy
import fcntl
import hashlib
import json
import os
import tempfile
import subprocess
import re
from .manage import UNIT
from .manage import ManagementError, runtime_config, validate_runtime_config, private_dir

from .codex_transport import DEFAULT_SETUP_TIMEOUT, DEFAULT_GENERATION_TIMEOUT

EDITABLE = ('model', 'model_reasoning_effort', 'web_search', 'sync_guild',
            'setup_timeout_seconds', 'generation_timeout_seconds')
TIMEOUT_DEFAULTS = {'setup_timeout_seconds': DEFAULT_SETUP_TIMEOUT,
                    'generation_timeout_seconds': DEFAULT_GENERATION_TIMEOUT}


def service_status(*, runner=subprocess.run):
    fields = ('ActiveState', 'SubState', 'Result', 'ExecMainStatus', 'NRestarts')
    try:
        result = runner(['systemctl', '--user', 'show', UNIT,
                         '--property=' + ','.join(fields)],
                        capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return {'available': False}
    if result.returncode:
        return {'available': False}
    status = {'available': True}
    for line in result.stdout.splitlines():
        key, sep, value = line.partition('=')
        if sep and key in fields and re.fullmatch(r'[a-zA-Z0-9_-]{1,40}', value):
            status[key] = value
    if not all(key in status for key in fields):
        return {'available': False}
    return status


def apply_settings(paths, expected_revision, confirmed, *, runner=subprocess.run):
    if confirmed is not True:
        raise ManagementError('봇 재시작 확인이 필요합니다.')
    with settings_lock(paths):
        if read_settings(paths)['revision'] != expected_revision:
            raise ManagementError('설정이 변경되었습니다. 다시 확인하세요.')
        try:
            result = runner(['systemctl', '--user', 'restart', UNIT],
                            capture_output=True, text=True, timeout=40)
        except (OSError, subprocess.TimeoutExpired):
            raise ManagementError('재시작을 확인하지 못했습니다. 서비스 상태를 확인하세요.') from None
        if result.returncode:
            raise ManagementError('재시작 실패. 저장된 설정은 유지됩니다.')
        return service_status(runner=runner)


def revision(config):
    return hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()


def read_settings(paths):
    config = runtime_config(paths)
    options = config.get('codex', {})
    values = {key: options.get(key, '') for key in EDITABLE if key != 'sync_guild'}
    values['web_search'] = options.get('web_search', 'disabled')
    values.update({key: options.get(key, default) for key, default in TIMEOUT_DEFAULTS.items()})
    values['sync_guild'] = config['sync_guild']
    return {'revision': revision(config), 'values': values,
            'provider': config['provider'], 'applied': None}


@contextmanager
def settings_lock(paths):
    private_dir(paths.config)
    fd = os.open(paths.config/'settings.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def atomic_json(target, value):
    """Replace within the same private directory; fsync before and after rename."""
    fd, name = tempfile.mkstemp(prefix='.settings-', dir=target.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, ensure_ascii=True, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, target)
        directory = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def save_settings(paths, changes, expected_revision):
    with settings_lock(paths):
        current = runtime_config(paths)
        if revision(current) != expected_revision:
            raise ManagementError('다른 작업에서 설정을 변경했습니다. 새로고침 후 다시 저장하세요.')
        if not isinstance(changes, dict) or not set(changes) <= set(EDITABLE):
            raise ManagementError('지원하지 않는 설정입니다.')
        updated = copy.deepcopy(current)
        options = updated.setdefault('codex', {})
        for key, value in changes.items():
            if key == 'sync_guild':
                updated[key] = value
            elif value == '' and key in ('model', 'model_reasoning_effort'):
                options.pop(key, None)
            else:
                options[key] = value
        try:
            validate_runtime_config(updated)
        except (ValueError, TypeError):
            raise ManagementError('설정 값이 올바르지 않습니다. 형식과 허용 범위를 확인하세요.') from None
        atomic_json(paths.config/'runtime.json', updated)
        result = read_settings(paths)
        if result['revision'] != revision(updated):
            raise ManagementError('저장 후 설정 확인에 실패했습니다.')
        return result
