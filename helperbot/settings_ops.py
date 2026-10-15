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


def service_status(*, unit=UNIT, runner=subprocess.run):
    from .web_service import WEB_UNIT
    if unit not in (UNIT, WEB_UNIT):
        raise ValueError('Unsupported service unit')
    required = ('ActiveState', 'SubState', 'Result', 'ExecMainStatus', 'NRestarts')
    fields = required + ('LoadState', 'UnitFileState')
    try:
        result = runner(['systemctl', '--user', 'show', unit,
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
    if not all(key in status for key in required):
        return {'available': False}
    return status


def operator_overview(*, runner=subprocess.run, bot_status=None):
    """Read-only snapshots, never readiness or runtime-settings attestation."""
    from .web_service import WEB_UNIT
    report = {'applied': None}
    for key, unit in (('bot', UNIT), ('web', WEB_UNIT)):
        status = (bot_status if key == 'bot' and bot_status is not None
                  else service_status(unit=unit, runner=runner))
        command = None
        if not status['available']:
            message = '사용자 systemd 상태 확인 불가. 서비스 계정의 로그인 세션에서 확인하세요.'
        elif status.get('LoadState') == 'not-found':
            message = '서비스 미설치. 설치된 CLI와 경로를 확인한 뒤 install 또는 gui install을 실행하세요.'
        elif status.get('LoadState') != 'loaded':
            message = '서비스 로드 상태를 확인하지 못했습니다. 로컬에서 유닛 구성을 점검하세요.'
        elif status['ActiveState'] == 'inactive':
            message = '서비스가 중지되어 있습니다. 필요할 때만 아래 명령으로 시작하세요.'
            command = 'systemctl --user start ' + unit
        elif status['ActiveState'] == 'failed':
            message = '서비스 실패. 원인을 점검한 뒤 명시적으로 재시작하세요.'
            command = 'systemctl --user restart ' + unit
        else:
            message = '서비스 상태 스냅샷입니다. active도 Discord 연결·설정 적용 성공의 증거는 아닙니다.'
        report[key] = {'unit': unit, 'status': status, 'message': message, 'command': command}
    return report


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
            'provider': config['provider'], 'applied': None,
            'configured': list(options)}


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
    """Partial update; an empty optional value explicitly removes its override.

    Clear commands are not persisted as empty strings. The resulting runtime
    config still passes the shared provider validator under the revision lock.
    """
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
            elif value == '' and key in ('model', 'model_reasoning_effort', 'web_search',
                                         *TIMEOUT_DEFAULTS):
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
