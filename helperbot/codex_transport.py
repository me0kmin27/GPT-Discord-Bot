"""Official Codex app-server stdio transport, NOT an enabled hosted provider.

No tokens/endpoints are implemented here: official CLI owns OAuth. The security
readiness gate is intentionally unconditional, not a configuration switch.
"""
import asyncio
import json
import os
import signal
from collections import deque
from pathlib import Path
from tempfile import TemporaryDirectory

from .provider import ProviderReply, ProviderUnavailable

CODEX_VERSION = '0.162.1'
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


def require_supported_transport():
    raise ProviderUnavailable(
        'Codex zero-tools control is not verified for pinned app-server; '
        'transport implemented, activation blocked (hosted permission is a separate gate)')


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


class CodexOAuthProvider:
    """Implemented managed-OAuth path, hard-gated before filesystem/process access."""
    def __init__(self, executable, data, *, timeout=20):
        self.executable = Path(executable)
        self.data = Path(data)
        self.timeout = timeout

    def _command(self):
        return (str(self.executable), '-c', 'cli_auth_credentials_store="file"',
                '-c', 'forced_login_method="chatgpt"', 'app-server')

    async def answer(self, request):
        require_supported_transport()
        payload = prepare_request(request)
        try:
            return await asyncio.wait_for(self._answer(request, payload), self.timeout)
        except asyncio.TimeoutError:
            raise
        except (KeyError, TypeError, ValueError, OSError, AttributeError):
            raise ProviderUnavailable('Codex transport unavailable') from None

    async def _answer(self, request, payload):
        # Runtime isolation is defense in depth, NOT a no-tools boundary.
        from .manage import private_dir
        data = private_dir(self.data)
        codex_home = private_dir(data / 'codex')  # Same home as official codex-login.
        with TemporaryDirectory(prefix='request-', dir=data) as directory:
            root = Path(directory)
            home = private_dir(root / 'home')
            cwd = private_dir(root / 'work')
            env = {'HOME': str(home), 'CODEX_HOME': str(codex_home),
                   'PATH': os.defpath, 'LANG': 'C.UTF-8', 'TMPDIR': str(root)}
            async with StdioClient(self._command(), cwd=cwd, env=env) as client:
                await client.initialize()
                account = await client.rpc('account/read', {'refreshToken': False})
                if (account.get('account') or {}).get('type') != 'chatgpt':
                    raise ProviderUnavailable('Codex managed ChatGPT login required')
                thread = await client.rpc('thread/start', {
                    'ephemeral': True, 'cwd': str(cwd), 'sandbox': 'read-only',
                    'approvalPolicy': 'untrusted', 'approvalsReviewer': 'user',
                    'developerInstructions': request.instruction})
                thread_id = thread['thread']['id']
                if thread['thread'].get('ephemeral') is not True or thread['thread'].get('path') is not None:
                    raise ProviderUnavailable('Codex ephemeral thread required')
                schema = {'type': 'object', 'additionalProperties': False,
                          'required': ['text', 'case_ids'], 'properties': {
                              'text': {'type': 'string'},
                              'case_ids': {'type': 'array', 'items': {'type': 'integer'}}}}
                turn = await client.rpc('turn/start', {
                    'threadId': thread_id, 'input': [{'type': 'text', 'text': payload}],
                    'outputSchema': schema})
                return await client.completion(thread_id, turn['turn']['id'], request.evidence)


class StdioClient:
    """One bounded sequential JSON-RPC connection; no subprocess shell or logging."""
    def __init__(self, command, *, cwd, env, timeout=20):
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 120:
            raise ValueError('Invalid Codex timeout')
        self.timeout = timeout
        self.deadline = None
        self.command, self.cwd, self.env = command, cwd, env
        self.process = None
        self.sequence = 0
        self.events = deque()
        self.wire_bytes = 0
        self.event_count = 0

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
                raise asyncio.TimeoutError()
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
        except asyncio.TimeoutError:
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
        except asyncio.TimeoutError:
            raise
        except (OSError, ValueError, RecursionError):
            raise ProviderUnavailable('Codex invalid or excessive protocol output') from None
        if 'method' in message:
            if (not isinstance(message['method'], str)
                    or not isinstance(message.get('params'), dict)):
                raise ProviderUnavailable('Codex malformed notification or request')
            if message['method'] in ('item/started', 'item/completed'):
                item = message['params'].get('item')
                if not isinstance(item, dict) or item.get('type') not in ('userMessage', 'reasoning', 'agentMessage'):
                    raise ProviderUnavailable('Codex tool or unknown item rejected')
            if 'id' in message:
                # Includes approvals, dynamic tools, external token refresh, and
                # UNKNOWN future requests. Never approve or supply credentials.
                await self.send({'id': message['id'], 'error': {
                    'code': -32601, 'message': 'Client requests are not supported'}})
                raise ProviderUnavailable('Codex server request rejected')
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
            if (type(message.get('id')) is not int or message['id'] != self.sequence
                    or 'error' in message or not isinstance(message.get('result'), dict)):
                raise ProviderUnavailable('Codex protocol failure')
            return message['result']

    async def completion(self, thread_id, turn_id, evidence):
        # Buffer only; never expose partial text before terminal success.
        final = None
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
                           for item in turn['items']):
                        raise ValueError()
                    if method == 'turn/completed':
                        if turn['status'] != 'completed' or turn.get('error') is not None or not final:
                            raise ValueError()
                        reply = json.loads(final)
                        if (not isinstance(reply, dict) or set(reply) != {'text', 'case_ids'}
                                or not isinstance(reply['text'], str) or not reply['text'].strip()
                                or len(reply['text']) > 1000 or not isinstance(reply['case_ids'], list)
                                or len(reply['case_ids']) > 3
                                or any(type(i) is not int for i in reply['case_ids'])
                                or len(set(reply['case_ids'])) != len(reply['case_ids'])
                                or not set(reply['case_ids']).issubset({item['id'] for item in evidence})):
                            raise ValueError()
                        return ProviderReply(reply['text'], tuple(reply['case_ids']))
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
