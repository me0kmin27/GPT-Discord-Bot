"""Opt-in synthetic inference probe; runnable against an older installation.

No Discord connection, database, user question or conversation is read. The
installed public provider owns app-isolated OAuth. --live may consume plan usage.
Only fixed labels, bounded codes, durations, answer length and internal locations
are emitted. No raw exceptions, bodies, answers, prompts, auth or logs.
"""
import argparse
import asyncio
import json
import logging
from contextlib import redirect_stdout, redirect_stderr
import os
import time
from pathlib import Path


# Exact local messages only. Unknown provider text is never echoed or parsed.
FAILURES = {
    'Codex managed ChatGPT login required': ('account', 'login_required'),
    'Codex effective configuration restrictions rejected': ('config', 'config_rejected'),
    'Codex application home must not contain operator configuration': ('prepare', 'config_rejected'),
    'Codex application auth must not be symlinked': ('prepare', 'auth_path_rejected'),
    'Codex application auth requires private owner-only file': ('prepare', 'auth_path_rejected'),
    'Codex request bounds or shape rejected': ('prepare', 'request_rejected'),
    'Codex requires a supported POSIX sandbox platform': ('prepare', 'platform_rejected'),
    'Codex version or isolated home mismatch': ('initialize', 'version_home_mismatch'),
    'Codex ephemeral thread required': ('thread', 'thread_rejected'),
    'Codex effective thread restrictions rejected': ('thread', 'thread_rejected'),
    'Codex response contract rejected': ('completion', 'response_rejected'),
    '공급자 응답/출처 검증 실패': ('response', 'response_rejected'),
    'Codex turn error': ('completion', 'turn_error'),
    'Codex protocol failure': ('protocol', 'rpc_rejected'),
    'Codex unsupported notification': ('protocol', 'notification_rejected'),
    'Codex malformed notification or request': ('protocol', 'notification_rejected'),
    'Codex tool or unknown item rejected': ('protocol', 'tool_item_rejected'),
    'Codex server request rejected': ('protocol', 'server_request_rejected'),
    'Codex remote control must remain disabled': ('protocol', 'remote_control_rejected'),
    'Codex notification queue exceeded': ('protocol', 'protocol_limit'),
    'Codex invalid or excessive protocol output': ('protocol', 'protocol_output_rejected'),
    'Codex request transport failure': ('protocol', 'transport_unavailable'),
    'Codex transport unavailable': ('transport', 'transport_unavailable'),
}
INTERNAL_FILES = frozenset(('codex_transport.py', 'provider.py', 'async_utils.py',
                            'service.py', 'manage.py', 'inference_probe.py'))


def safe_failure(error):
    try:
        from helperbot.provider import ProviderUnavailable
    except ImportError:
        return {'stage': 'prepare', 'category': 'installation_unavailable',
                'exception': 'ImportError', 'rpc_code': None, 'http_status': None, 'locations': []}
    stage, category, exception = 'answer', 'unknown', 'Other'
    if isinstance(error, ProviderUnavailable):
        exception = 'ProviderUnavailable'
        if error.args and type(error.args[0]) is str:
            stage, category = FAILURES.get(error.args[0], (stage, category))
    elif isinstance(error, (TimeoutError, asyncio.TimeoutError)):
        category, exception = 'timeout', 'TimeoutError'
    elif isinstance(error, OSError):
        category, exception = 'local_io', 'OSError'
    locations = []
    tb = error.__traceback__
    while tb is not None:
        path = Path(tb.tb_frame.f_code.co_filename)
        if path.parent.name == 'helperbot' and path.name in INTERNAL_FILES:
            locations.append({'file': path.name, 'line': tb.tb_lineno})
        tb = tb.tb_next
    rpc_code = getattr(error, 'rpc_code', None) if isinstance(error, ProviderUnavailable) else None
    if type(rpc_code) is not int or not -(2**31) <= rpc_code < 2**31:
        rpc_code = None
    return {'stage': stage, 'category': category, 'exception': exception,
            'rpc_code': rpc_code, 'http_status': None, 'locations': locations[-8:]}


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError()


def main(argv=None):
    parser = SafeParser(prog='inference-probe', description=__doc__, allow_abbrev=False)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--data-dir', type=Path)
    try:
        args = parser.parse_args(argv)
    except ValueError:
        print(json.dumps({'stage': 'arguments', 'answer_success': False}))
        return 2
    if not args.live:
        print(json.dumps({'stage': 'opt_in', 'answer_success': False}))
        return 2
    started = time.monotonic()
    previous_logging = logging.root.manager.disable
    try:
        logging.disable(logging.CRITICAL)
        with open(os.devnull, 'w') as sink, redirect_stdout(sink), redirect_stderr(sink):
            from helperbot.provider import build_provider, Request
            from helperbot.async_utils import wait_owned
            data = args.data_dir or Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))) / 'discord-helper'
            provider = build_provider('codex-oauth', data=data.absolute())
            async def invoke():
                return await wait_owned(provider.answer(Request((1, 2),
                    'What is two plus two? Reply briefly.', (), ())), 20)
            reply = asyncio.run(invoke())
            if (type(reply.text) is not str or not reply.text.strip() or len(reply.text) > 1000
                    or '\x00' in reply.text or not isinstance(reply.case_ids, (tuple, list)) or reply.case_ids):
                from helperbot.provider import ProviderUnavailable
                raise ProviderUnavailable('Codex response contract rejected')
            record = {'stage': 'complete', 'answer_success': True, 'answer_length': len(reply.text)}
            status = 0
    except Exception as error:
        record = dict(safe_failure(error), answer_success=False, answer_length=0)
        status = 1
    finally:
        logging.disable(previous_logging)
    record['duration_ms'] = int((time.monotonic() - started) * 1000)
    print(json.dumps(record))
    return status


if __name__ == '__main__':
    raise SystemExit(main())
