"""Real signed-out public answer path; no existing auth or live inference."""
import asyncio
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from helperbot.codex_transport import CodexOAuthProvider
from helperbot.provider import Request, ProviderUnavailable
from probe_codex import resolve_executable


async def probe(executable, scratch):
    executable = resolve_executable(executable)
    with TemporaryDirectory(prefix='codex-answer-probe-', dir=scratch) as directory:
        data = Path(directory)
        adapter = CodexOAuthProvider(executable, data)
        try:
            await adapter.answer(Request((1, 2), 'credential-free diagnostic', (), ()))
        except ProviderUnavailable as exc:
            assert str(exc) == 'Codex managed ChatGPT login required', str(exc)
        else:
            raise AssertionError('Expected signed-out official account')
        assert not (data / 'codex/auth.json').exists()
        assert not list(data.glob('request-*'))
        return {'executable': str(executable), 'public_answer': 'auth-needed',
                'existing_auth_accessed': False, 'auth_created': False,
                'live_inference': False, 'request_cleanup': True}


if __name__ == '__main__':
    print(json.dumps(asyncio.run(probe(Path(sys.argv[1]).absolute(), Path(sys.argv[2]).absolute())), indent=2))
