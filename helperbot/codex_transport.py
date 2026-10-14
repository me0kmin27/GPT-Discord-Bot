"""Explicitly selected local official Codex OAuth transport.

Restrictions mitigate execution effects; they do not prove a zero-tool registry.
The official CLI owns application-isolated OAuth; no credential copying.
"""
import asyncio
import json
import os
import signal
import stat
import platform
from collections import deque
from contextlib import AsyncExitStack
from pathlib import Path
from tempfile import TemporaryDirectory

from .provider import ProviderReply, ProviderUnavailable
from .async_utils import OwnedDeadlineExceeded, wait_owned

CODEX_VERSION = '0.162.1'
DEFAULT_SETUP_TIMEOUT = 3
DEFAULT_GENERATION_TIMEOUT = 20
MAX_FRAME = 65536
MAX_WIRE = 1048576
MAX_EVENTS = 2048
MAX_QUEUED = 64
NOTIFICATIONS = frozenset({
    'thread/started', 'thread/status/changed', 'thread/tokenUsage/updated',
    'turn/started', 'turn/completed', 'item/started', 'item/completed',
    'item/agentMessage/delta', 'item/reasoning/summaryTextDelta',
    'item/reasoning/textDelta', 'item/reasoning/summaryPartAdded',
    'account/updated', 'account/rateLimits/updated', 'error'})


def validate_options(options=None):
    """Only operator search/model selection; never arbitrary Codex config."""
    if options is None:
        return {}
    if not isinstance(options, dict) or not set(options) <= {
            'web_search', 'model', 'model_reasoning_effort',
            'setup_timeout_seconds', 'generation_timeout_seconds'}:
        raise ValueError('Invalid Codex operator options')
    for key, value in options.items():
        if key in ('setup_timeout_seconds', 'generation_timeout_seconds'):
            ceiling = 30 if key == 'setup_timeout_seconds' else 120
            if type(value) not in (int, float) or not 0 < value <= ceiling:
                raise ValueError('Invalid Codex timeout')
            continue
        if (not isinstance(value, str) or not 0 < len(value) <= 128
                or any(not (c.isascii() and (c.isalnum() or c in '._-/')) for c in value)
                or (key == 'web_search' and value not in ('disabled', 'live'))):
            raise ValueError('Invalid Codex operator options')
    return dict(options)


def execution_config(options=None):
    """Controls verified against rust-v0.162.1 config schema and tool registry.

    Do not use removed js_repl/apply_patch flags as imaginary security controls.
    Read-only sandbox blocks writes/network, not all host reads or built-in tools.
    """
    config = {
        'cli_auth_credentials_store': 'file', 'forced_login_method': 'chatgpt',
        'sandbox_mode': 'read-only', 'approval_policy': 'never',
        'approvals_reviewer': 'user', 'web_search': 'disabled',
        'allow_login_shell': False, 'shell_environment_policy.inherit': 'none',
        'shell_environment_policy.set': {}, 'mcp_servers': {},
        'project_doc_max_bytes': 0, 'history.persistence': 'none',
        'tools.update_plan.enabled': False,
        'tools.experimental_request_user_input.enabled': False,
        'model_provider': 'openai',
    }
    for feature in ('shell_tool', 'view_image', 'code_mode', 'code_mode_only',
                    'apps', 'plugins', 'multi_agent', 'multi_agent_v2',
                    'browser_use', 'computer_use', 'image_generation',
                    'shell_snapshot', 'hooks', 'memories', 'request_permissions_tool'):
        config['features.' + feature] = False
    config['features.skip_host_skill_discovery'] = True
    config.update({key: value for key, value in validate_options(options).items()
                   if key not in ('setup_timeout_seconds', 'generation_timeout_seconds')})
    return config


def validate_config(config, options=None):
    """Verify resolved controls, not whether an arbitrary warning was emitted."""
    try:
        for key, expected in execution_config(options).items():
            if key.startswith('tools.'):
                continue  # Public config/read omits these utility switches.
            actual = config
            for part in key.split('.'):
                actual = actual[part]
            if actual != expected or type(actual) is not type(expected):
                raise ValueError()
        for key in ('notify', 'hooks', 'model_providers', 'plugins', 'skills',
                    'model_instructions_file', 'model_catalog_json', 'instructions',
                    'developer_instructions', 'default_permissions', 'permissions',
                    'experimental_thread_store', 'openai_base_url'):
            if config.get(key):
                raise ValueError()
        if config.get('chatgpt_base_url', 'https://chatgpt.com/backend-api/') != 'https://chatgpt.com/backend-api/':
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        raise ProviderUnavailable('Codex effective configuration restrictions rejected') from None


def command_for(executable, options=None):
    args = [str(executable)]
    for key, value in execution_config(options).items():
        # TOML scalar values; empty inline table differs from JSON object syntax.
        encoded = '{}' if value == {} else json.dumps(value)
        args.extend(('-c', key + '=' + encoded))
    return tuple(args + ['app-server'])


def prepare_request(request):
    """Bound before allocation/IO; omit Discord identities and storage metadata."""
    try:
        def text(value, limit=2000):
            if not isinstance(value, str) or not value.strip() or len(value) > limit:
                raise ValueError()
            return value
        text(request.instruction, 4096)
        if (not isinstance(request.history, tuple) or len(request.history) > 8
                or not isinstance(request.evidence, tuple) or len(request.evidence) > 3):
            raise ValueError()
        evidence = []
        for item in request.evidence:
            if type(item['id']) is not int or not 0 < item['id'] < 2**63:
                raise ValueError()
            evidence.append({'id': item['id'], 'question': text(item['question']),
                             'solution': text(item['solution'])})
        if len({item['id'] for item in evidence}) != len(evidence):
            raise ValueError()
        payload = json.dumps({'question': text(request.question),
                              'history': [text(value) for value in request.history],
                              'evidence': evidence}, ensure_ascii=False, allow_nan=False)
        if len(payload.encode()) + len(request.instruction.encode()) > 49152:
            raise ValueError()
        return payload
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ProviderUnavailable('Codex request bounds or shape rejected') from None


def render_web_sources(reply, searched):
    """Model citations, not verified retrieval; never fetch model-provided URLs."""
    from urllib.parse import urlsplit
    sources = reply['web_sources']
    if (not isinstance(sources, list) or len(sources) > 3
            or (sources and not searched)):
        raise ValueError()
    for url in sources:
        if (not isinstance(url, str) or not 0 < len(url) <= 512
                or any(c.isspace() or ord(c) < 32 or c in '<>\\' for c in url)):
            raise ValueError()
        parsed = urlsplit(url)
        if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError()
    if len(set(sources)) != len(sources):
        raise ValueError()
    label = ('Model-cited web sources (not independently verified):\n' + '\n'.join(sources)
             if sources else 'No web sources supplied; current facts unverified.')
    text = reply['text'] + '\n\n' + label
    if len(text) > 1000:
        raise ValueError()
    return text


class CodexOAuthProvider:
    """Local managed OAuth with bounded, isolated request processes."""
    manages_deadlines = True

    def __init__(self, executable, data, *, timeout=DEFAULT_GENERATION_TIMEOUT,
                 setup_timeout=DEFAULT_SETUP_TIMEOUT, options=None):
        if type(timeout) not in (int, float) or not 0 < timeout <= 120:
            raise ValueError('Invalid Codex timeout')
        if type(setup_timeout) not in (int, float) or not 0 < setup_timeout <= 30:
            raise ValueError('Invalid Codex timeout')
        self.options = validate_options(options)
        self.executable = Path(executable)
        self.data = Path(data)
        if not self.executable.is_absolute() or not self.data.is_absolute():
            raise ValueError('Codex executable and data paths must be absolute')
        self.timeout = self.options.get('generation_timeout_seconds', timeout)
        self.setup_timeout = self.options.get('setup_timeout_seconds', setup_timeout)

    def _command(self):
        return command_for(self.executable, self.options)

    async def answer(self, request):
        payload = prepare_request(request)
        if platform.system() not in ('Darwin', 'Linux'):
            raise ProviderUnavailable('Codex requires a supported POSIX sandbox platform')
        try:
            # Each phase owns its budget; this wrapper owns cancellation/cleanup,
            # not a competing total timer that could steal generation time.
            return await wait_owned(self._answer(request, payload), None)
        except (asyncio.TimeoutError, TimeoutError):
            raise
        except (KeyError, TypeError, ValueError, OSError, AttributeError):
            raise ProviderUnavailable('Codex transport unavailable') from None

    async def _answer(self, request, payload):
        async with AsyncExitStack() as stack:
            client, thread_id, web_search = await wait_owned(
                self._prepare(request, stack), self.setup_timeout, stage='preparation')
            # Begin a new absolute transport budget; notifications/RPCs never reset it.
            client.timeout = self.timeout
            client.deadline_stage = 'generation'
            client.deadline = asyncio.get_running_loop().time() + self.timeout
            return await wait_owned(self._generate(client, thread_id, web_search, request, payload),
                                    self.timeout, stage='generation')

    async def _prepare(self, request, stack):
        # Runtime isolation is defense in depth, NOT a no-tools boundary.
        from .manage import private_dir
        data = private_dir(self.data)
        codex_home = private_dir(data / 'codex')  # Same home as official codex-login.
        auth = codex_home / 'auth.json'
        if auth.is_symlink():
            raise ProviderUnavailable('Codex application auth must not be symlinked')
        if auth.exists():
            metadata = auth.stat()
            if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid()
                    or metadata.st_mode & 0o077):
                raise ProviderUnavailable('Codex application auth requires private owner-only file')
        if (codex_home / 'config.toml').exists() or (codex_home / 'config.toml').is_symlink():
            raise ProviderUnavailable('Codex application home must not contain operator configuration')
        directory = stack.enter_context(TemporaryDirectory(prefix='request-', dir=data))
        root = Path(directory)
        home = private_dir(root / 'home')
        cwd = private_dir(root / 'work')
        env = {'HOME': str(home), 'CODEX_HOME': str(codex_home),
               'PATH': os.defpath, 'LANG': 'C.UTF-8', 'TMPDIR': str(root)}
        web_search = self.options.get('web_search') == 'live'
        instruction = request.instruction + (
            " Only hosted web search is permitted; use it for current facts/weather. "
            "Never use shell, files, local network, MCP or other tools. "
            "Minimize search queries; do not send private history/evidence to search. "
            "Return web_sources as at most 3 HTTP(S) source URLs actually used, "
            "not citation tokens; keep answer plus URLs below 900 characters. "
            "Web sources are not verified cases. If search is unavailable or insufficient, "
            "say current facts cannot be verified; never invent sources or current weather."
            if web_search else " Do not execute tools.")
        client = await stack.enter_async_context(StdioClient(
            self._command(), cwd=cwd, env=env, timeout=self.setup_timeout,
            web_search=web_search, deadline_stage='preparation'))
        await client.initialize()
        resolved = await client.rpc('config/read', {'includeLayers': False})
        validate_config(resolved['config'], self.options)
        account = await client.rpc('account/read', {'refreshToken': False})
        if (account.get('account') or {}).get('type') != 'chatgpt':
            raise ProviderUnavailable('Codex managed ChatGPT login required')
        thread = await client.rpc('thread/start', {
            'ephemeral': True, 'cwd': str(cwd), 'sandbox': 'read-only',
            'approvalPolicy': 'never', 'approvalsReviewer': 'user',
            'developerInstructions': instruction})
        thread_id = thread['thread']['id']
        if thread['thread'].get('ephemeral') is not True or thread['thread'].get('path') is not None:
            raise ProviderUnavailable('Codex ephemeral thread required')
        if (thread.get('sandbox') != {'type': 'readOnly', 'networkAccess': False}
                or thread.get('approvalPolicy') != 'never'
                or thread.get('approvalsReviewer') != 'user'
                or thread.get('cwd') != str(cwd)
                or thread.get('modelProvider') != 'openai'):
            raise ProviderUnavailable('Codex effective thread restrictions rejected')
        return client, thread_id, web_search

    async def _generate(self, client, thread_id, web_search, request, payload):
        schema = {'type': 'object', 'additionalProperties': False,
                  'required': ['text', 'case_ids'], 'properties': {
                      'text': {'type': 'string'},
                      'case_ids': {'type': 'array', 'items': {'type': 'integer'}}}}
        if web_search:
            schema['required'].append('web_sources')
            schema['properties']['web_sources'] = {
                'type': 'array', 'items': {'type': 'string'}}
        turn = await client.rpc('turn/start', {
            'threadId': thread_id, 'input': [{'type': 'text', 'text': payload}],
            'sandboxPolicy': {'type': 'readOnly', 'networkAccess': False},
            'approvalPolicy': 'never',
            'outputSchema': schema})
        return await client.completion(thread_id, turn['turn']['id'], request.evidence)


class StdioClient:
    """One bounded sequential JSON-RPC connection; no subprocess shell or logging."""
    def __init__(self, command, *, cwd, env, timeout=20, web_search=False, deadline_stage='transport'):
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 120:
            raise ValueError('Invalid Codex timeout')
        self.timeout = timeout
        self.deadline = None
        self.deadline_stage = deadline_stage
        self.command, self.cwd, self.env = command, cwd, env
        self.process = None
        self.sequence = 0
        self.events = deque()
        self.wire_bytes = 0
        self.event_count = 0
        self.configuration_warning = False
        self.web_search = web_search


    async def __aenter__(self):
        self.deadline = asyncio.get_running_loop().time() + self.timeout
        spawning = asyncio.create_task(asyncio.create_subprocess_exec(
            *self.command, cwd=self.cwd, env=self.env,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, start_new_session=True,
            limit=MAX_FRAME))
        try:
            self.process = await asyncio.shield(spawning)
        except BaseException:
            # Own the child even if cancellation arrives between fork and return.
            # Shield the OS spawn, not the inference. Never lose its process handle.
            try:
                self.process = await self._settle(spawning)
            finally:
                await self.__aexit__()
            raise
        return self

    @staticmethod
    async def _settle(task, *, propagate_cancel=False):
        cancelled = False
        while True:
            try:
                result = await asyncio.shield(task)
                break
            except asyncio.CancelledError:
                cancelled = True
                if task.done():
                    result = task.result()
                    break
        if cancelled and propagate_cancel:
            raise asyncio.CancelledError()
        return result

    async def _bounded(self, awaitable):
        remaining = max(0, self.deadline - asyncio.get_running_loop().time())
        task = asyncio.ensure_future(awaitable)
        try:
            done, _ = await asyncio.wait((task,), timeout=remaining)
            if not done:
                elapsed = asyncio.get_running_loop().time() - (self.deadline - self.timeout)
                raise OwnedDeadlineExceeded(self.deadline_stage, elapsed, self.timeout)
            return task.result()
        finally:
            if not task.done():
                task.cancel()
                await self._settle(asyncio.ensure_future(asyncio.gather(task, return_exceptions=True)))

    async def _reap(self):
        # After group kill, discard buffered bytes so asyncio can close a paused
        # pipe. Do not accumulate/log them, even on excessive-output failures.
        while await self.process.stdout.read(MAX_FRAME):
            pass
        await self.process.wait()

    async def __aexit__(self, *exc):
        if self.process is not None:
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self.process.stdin.close()
            # SIGKILL is intentional: no model/tool work may continue after a
            # privacy cancellation. No reliance on an unacknowledged interrupt RPC.
            waiting = asyncio.create_task(self._reap())
            try:
                await self._settle(waiting, propagate_cancel=True)
            finally:
                self.events.clear()
        self.events.clear()

    async def send(self, message):
        try:
            frame = json.dumps(message, ensure_ascii=False, allow_nan=False).encode() + b'\n'
            if len(frame) > MAX_FRAME:
                raise ValueError()
            self.process.stdin.write(frame)
            await self._bounded(self.process.stdin.drain())
        except (asyncio.TimeoutError, TimeoutError):
            raise
        except (OSError, ValueError, TypeError):
            raise ProviderUnavailable('Codex request transport failure') from None

    async def receive(self):
        try:
            frame = await self._bounded(self.process.stdout.readline())
            self.wire_bytes += len(frame)
            self.event_count += 1
            if (not frame or len(frame) > MAX_FRAME or not frame.endswith(b'\n')
                    or self.wire_bytes > MAX_WIRE or self.event_count > MAX_EVENTS):
                raise ValueError()
            message = json.loads(frame)
            if not isinstance(message, dict):
                raise ValueError()
        except (asyncio.TimeoutError, TimeoutError):
            raise
        except (OSError, ValueError, RecursionError):
            raise ProviderUnavailable('Codex invalid or excessive protocol output') from None
        if 'method' in message:
            if (not isinstance(message['method'], str)
                    or not isinstance(message.get('params'), dict)):
                raise ProviderUnavailable('Codex malformed notification or request')
            if 'id' in message:
                # Includes approvals, dynamic tools, external token refresh, and
                # UNKNOWN future requests. Never approve or supply credentials.
                await self.send({'id': message['id'], 'error': {
                    'code': -32601, 'message': 'Client requests are not supported'}})
                raise ProviderUnavailable('Codex server request rejected')
            if message['method'] == 'warning':
                # Pinned v0.162.1 WarningNotification: advisory text, optional
                # nullable thread target. Never retain/log the warning body.
                params = message['params']
                thread_id = params.get('threadId')
                if (not isinstance(params.get('message'), str)
                        or (thread_id is not None and not isinstance(thread_id, str))):
                    raise ProviderUnavailable('Codex malformed notification or request')
                return {'method': 'warning', 'params':
                        {'threadId': thread_id} if thread_id is not None else {}}
            if message['method'] in ('item/started', 'item/completed'):
                message['params']['item'] = self.checked_item(message['params'].get('item'))
            if message['method'] in ('turn/started', 'turn/completed'):
                turn = message['params'].get('turn')
                if not isinstance(turn, dict) or not isinstance(turn.get('items'), list):
                    raise ProviderUnavailable('Codex malformed notification or request')
                turn['items'] = [self.checked_item(item) for item in turn['items']]
            if message['method'] == 'configWarning':
                self.configuration_warning = True
                # Notices are not evidence of invalid configuration, regardless
                # of arrival time. Resolved controls/thread policy are validated.
                return {'method': 'configWarning', 'params': {}}
            if message['method'] == 'remoteControl/status/changed':
                if message.get('params', {}).get('status') != 'disabled':
                    raise ProviderUnavailable('Codex remote control must remain disabled')
                return message
            if (message['method'] not in NOTIFICATIONS
                    or not isinstance(message.get('params'), dict)):
                raise ProviderUnavailable('Codex unsupported notification')
            if message['method'] == 'error':
                raise ProviderUnavailable('Codex turn error')
        return message

    def checked_item(self, item):
        """Validate pinned webSearch envelope; discard queries/results before queuing.

        There is no item status in 0.162.1: lifecycle is item/started/completed.
        Actions and opaque results are not proof that a URL was fetched.
        """
        try:
            if not isinstance(item, dict):
                raise ValueError()
            if item.get('type') in ('userMessage', 'reasoning', 'agentMessage'):
                return item
            if not self.web_search or item.get('type') != 'webSearch':
                raise ValueError()
            if (not {'type', 'id', 'query', 'action'} <= set(item)
                    or not set(item) <= {'type', 'id', 'query', 'action', 'results'}
                    or not isinstance(item['id'], str) or not 0 < len(item['id']) <= 256
                    or not isinstance(item['query'], str)
                    or (item.get('results') is not None and not isinstance(item['results'], list))):
                raise ValueError()
            action = item['action']
            if action is not None:
                fields = {'search': ('query', 'queries'), 'openPage': ('url',),
                          'findInPage': ('url', 'pattern'), 'other': ()}
                if not isinstance(action, dict) or not isinstance(action.get('type'), str):
                    raise ValueError()
                allowed = fields.get(action['type'])
                if allowed is None or not set(action) <= {'type', *allowed}:
                    raise ValueError()
                for key in allowed:
                    value = action.get(key)
                    if value is None:
                        continue
                    if key == 'queries':
                        if not isinstance(value, list) or any(not isinstance(q, str) for q in value):
                            raise ValueError()
                    elif not isinstance(value, str):
                        raise ValueError()
            return {'type': 'webSearch', 'id': item['id']}
        except (KeyError, TypeError, ValueError):
            raise ProviderUnavailable('Codex tool or unknown item rejected') from None

    async def rpc(self, method, params):
        self.sequence += 1
        await self.send({'id': self.sequence, 'method': method, 'params': params})
        while True:
            message = await self.receive()
            if 'method' in message:
                if len(self.events) >= MAX_QUEUED:
                    raise ProviderUnavailable('Codex notification queue exceeded')
                self.events.append(message)
                continue
            if type(message.get('id')) is int and message['id'] == self.sequence and 'error' in message:
                error = message['error']
                code = error.get('code') if isinstance(error, dict) else None
                raise ProviderUnavailable('Codex protocol failure', rpc_code=code)
            if (type(message.get('id')) is not int or message['id'] != self.sequence
                    or not isinstance(message.get('result'), dict)):
                raise ProviderUnavailable('Codex protocol failure')
            return message['result']

    async def completion(self, thread_id, turn_id, evidence):
        # Buffer only; never expose partial text before terminal success.
        final = None
        searched = False
        streams = {}
        completed = set()
        streamed_bytes = 0
        try:
            while True:
                event = self.events.popleft() if self.events else await self.receive()
                method, params = event['method'], event['params']
                if 'threadId' in params and params['threadId'] != thread_id:
                    raise ValueError()
                if 'turnId' in params and params['turnId'] != turn_id:
                    raise ValueError()
                if method == 'thread/started' and params['thread']['id'] != thread_id:
                    raise ValueError()
                if method.startswith('item/'):
                    if params['threadId'] != thread_id or params['turnId'] != turn_id:
                        raise ValueError()
                if method in ('item/started', 'item/completed'):
                    item = params['item']
                    if item['type'] == 'webSearch' and self.web_search:
                        searched = searched or method == 'item/completed'
                        continue
                    if item['type'] not in ('userMessage', 'reasoning', 'agentMessage'):
                        raise ValueError()  # Detection, NOT prevention of built-in execution.
                    if item['type'] == 'agentMessage' and method == 'item/completed':
                        item_id, text = item['id'], item['text']
                        if (not isinstance(text, str) or len(text.encode()) > 8192
                                or item_id in completed or len(completed) >= 32):
                            raise ValueError()
                        completed.add(item_id)
                        if item_id in streams and streams[item_id] != text:
                            raise ValueError()
                        if item.get('phase') == 'final_answer':
                            if final is not None:
                                raise ValueError()
                            final = text
                elif method == 'item/agentMessage/delta':
                    item_id, delta = params['itemId'], params['delta']
                    if not isinstance(item_id, str) or not isinstance(delta, str) or item_id in completed:
                        raise ValueError()
                    streamed_bytes += len(delta.encode())
                    if streamed_bytes > 32768 or (item_id not in streams and len(streams) >= 32):
                        raise ValueError()
                    streams[item_id] = streams.get(item_id, '') + delta
                    if len(streams[item_id].encode()) > 8192:
                        raise ValueError()
                elif method in ('turn/started', 'turn/completed'):
                    turn = params['turn']
                    if params['threadId'] != thread_id or turn['id'] != turn_id:
                        raise ValueError()
                    if any(item['type'] not in ('userMessage', 'reasoning', 'agentMessage')
                           and not (self.web_search and item['type'] == 'webSearch')
                           for item in turn['items']):
                        raise ValueError()
                    if method == 'turn/completed':
                        if turn['status'] != 'completed' or turn.get('error') is not None or not final:
                            raise ValueError()
                        reply = json.loads(final)
                        expected = {'text', 'case_ids', 'web_sources'} if self.web_search else {'text', 'case_ids'}
                        if (not isinstance(reply, dict) or set(reply) != expected
                                or not isinstance(reply['text'], str) or not reply['text'].strip()
                                or len(reply['text']) > 1000 or not isinstance(reply['case_ids'], list)
                                or len(reply['case_ids']) > 3
                                or any(type(i) is not int for i in reply['case_ids'])
                                or len(set(reply['case_ids'])) != len(reply['case_ids'])
                                or not set(reply['case_ids']).issubset({item['id'] for item in evidence})):
                            raise ValueError()
                        text = render_web_sources(reply, searched) if self.web_search else reply['text']
                        return ProviderReply(text, tuple(reply['case_ids']))
        except (KeyError, ValueError, TypeError, RecursionError):
            raise ProviderUnavailable('Codex response contract rejected') from None

    async def initialize(self):
        result = await self.rpc('initialize', {
            'clientInfo': {'name': 'discord_helper', 'version': '0.1.0'},
            'capabilities': {'experimentalApi': False}})
        if (not isinstance(result.get('userAgent'), str)
                or not result['userAgent'].startswith('discord_helper/' + CODEX_VERSION + ' ')
                or result.get('codexHome') != self.env.get('CODEX_HOME')):
            raise ProviderUnavailable('Codex version or isolated home mismatch')
        await self.send({'method': 'initialized', 'params': {}})
        return result
