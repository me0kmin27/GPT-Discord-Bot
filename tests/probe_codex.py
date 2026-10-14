"""Credential-free official binary probe. Never starts a thread/turn/login.

Usage: python tests/probe_codex.py /absolute/path/to/codex /private/scratch/root
Install ONLY the pinned official package under a project-local npm prefix.
"""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from helperbot.codex_transport import CODEX_VERSION, StdioClient


def resolve_executable(path):
    path = Path(path).absolute()
    if path.is_file():
        return path
    matches = [item for item in path.glob('@openai/codex-*/vendor/*/bin/codex') if item.is_file()]
    if len(matches) != 1:
        raise ValueError('Exactly one project-local native Codex binary is required')
    return matches[0]


async def probe(executable, scratch):
    executable = resolve_executable(executable)
    with TemporaryDirectory(prefix='codex-probe-', dir=scratch) as directory:
        root = Path(directory)
        home, codex, work = (root / name for name in ('home', 'codex', 'work'))
        for path in (home, codex, work):
            path.mkdir(mode=0o700)
        env = {'HOME': str(home), 'CODEX_HOME': str(codex), 'TMPDIR': str(root),
               'PATH': os.defpath, 'LANG': 'C.UTF-8'}
        version = subprocess.run([str(executable), '--version'], env=env, cwd=work,
                                 capture_output=True, timeout=15, check=True).stdout.decode().strip()
        assert version == 'codex-cli ' + CODEX_VERSION
        schema_dir = root / 'schema'
        subprocess.run([str(executable), 'app-server', 'generate-json-schema',
                        '--out', str(schema_dir)], env=env, cwd=work,
                       capture_output=True, timeout=30, check=True)
        hashes = {}
        for name, expected in {
                'ThreadStartParams': {'ephemeral', 'cwd', 'sandbox', 'approvalPolicy',
                                      'approvalsReviewer', 'developerInstructions'},
                'TurnStartParams': {'threadId', 'input', 'outputSchema'},
                'GetAccountParams': {'refreshToken'}}.items():
            raw = (schema_dir / 'v2' / (name + '.json')).read_bytes()
            properties = json.loads(raw)['properties']
            assert expected <= properties.keys()
            # Not a proof that every possible config combination lacks a control.
            assert not {'tools', 'toolChoice', 'tool_choice', 'allowedTools'} & properties.keys()
            hashes[name] = hashlib.sha256(raw).hexdigest()
        command = (str(executable), '-c', 'cli_auth_credentials_store="file"',
                   '-c', 'forced_login_method="chatgpt"', 'app-server')
        async with StdioClient(command, cwd=work, env=env) as client:
            initialized = await asyncio.wait_for(client.initialize(), 15)
            account = await asyncio.wait_for(client.rpc('account/read', {'refreshToken': False}), 15)
            assert account.get('account') is None
            assert initialized['codexHome'] == str(codex)
            process = client.process
        assert process.returncode is not None
        assert not (codex / 'auth.json').exists()
        return {'binary': version, 'initialize': 'ok', 'initialized': 'sent',
                'account': 'signed-out', 'auth_file_created': False,
                'thread_or_turn_started': False, 'process_reaped': True,
                'live_inference': False, 'zero_tools_verified': False,
                'generated_schema_sha256': hashes}


if __name__ == '__main__':
    print(json.dumps(asyncio.run(probe(Path(sys.argv[1]).absolute(), Path(sys.argv[2]).absolute())), indent=2))
