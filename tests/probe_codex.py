"""Credential-free official binary probe. Never starts a thread/turn/login.

Usage: python tests/probe_codex.py /absolute/path/to/codex /private/scratch/root
Install ONLY the pinned official package under a project-local npm prefix.
"""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from helperbot.codex_transport import CODEX_VERSION, StdioClient


async def probe(executable, scratch):
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
                'live_inference': False, 'zero_tools_verified': False}


if __name__ == '__main__':
    print(json.dumps(asyncio.run(probe(Path(sys.argv[1]).absolute(), Path(sys.argv[2]).absolute())), indent=2))
