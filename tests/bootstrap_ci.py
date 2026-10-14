"""Clean Linux bootstrap acceptance; no credentials, OAuth or Discord traffic."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    assert sys.platform == 'linux' and os.getuid() != 0
    source = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='helper-bootstrap-') as directory:
        home = Path(directory)
        env = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME=str(home/'.config'),
                   XDG_DATA_HOME=str(home/'.local/share'))
        for key in ('DISCORD_BOT_TOKEN', 'OPENAI_API_KEY', 'CODEX_HOME'):
            env.pop(key, None)
        def run(*args):
            result = subprocess.run(args, env=env, cwd=source, text=True, capture_output=True)
            assert result.returncode == 0, (args, result.stdout, result.stderr)
            print(result.stdout, flush=True)
            return result.stdout
        run('bash', str(source/'install.sh'), '--prepare-only')
        root = home/'.local/share/discord-helper-install'
        data = home/'.local/share/discord-helper'
        cli = str(root/'discord-helper')
        assert json.loads((root/'installer.json').read_text())['revision'] == run('git', 'rev-parse', 'HEAD').strip()
        assert run(str(data/'tools/node_modules/.bin/codex'), '--version').strip() == 'codex-cli 0.162.1'
        assert not (home/'.config/systemd/user/discord-helper.service').exists()
        assert not (home/'.config/discord-helper/credentials.json').exists()
        assert not (data/'codex/auth.json').exists()
        db = data/'state.db'
        before = hashlib.sha256(db.read_bytes()).hexdigest()
        stamp = (root/'software-ready').stat().st_mtime_ns
        run('bash', str(source/'install.sh'), '--prepare-only')
        assert hashlib.sha256(db.read_bytes()).hexdigest() == before
        assert (root/'software-ready').stat().st_mtime_ns == stamp
        run(cli, 'doctor')
        print('PASS: clean Linux checkout/venv/pinned Codex/offline schema + idempotent rerun. NOT live readiness.')


if __name__ == '__main__':
    main()
