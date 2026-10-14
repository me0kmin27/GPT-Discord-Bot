import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    # Never inherit tokens or personal auth into subprocess smoke tests.
    env = {'PATH': os.defpath, 'PYTHONPATH': str(ROOT)}
    return subprocess.run([sys.executable, '-m', 'helperbot', *args], cwd=ROOT, env=env, text=True, capture_output=True)


def test_offline_check_constructs_real_client_and_sqlite_without_token(tmp_path):
    result = run('--check', '--database', str(tmp_path / 'state.db'))
    assert result.returncode == 0, result.stderr
    assert '6 commands' in result.stdout
    assert 'disabled-codex' in result.stdout


def test_live_start_requires_token_without_reading_personal_credentials():
    result = run()
    assert result.returncode == 2
    assert 'DISCORD_BOT_TOKEN' in result.stderr


def test_provider_flag_cannot_enable_unreviewed_transport():
    result = run('--provider', 'codex-live', '--check')
    assert result.returncode == 2
    assert 'invalid choice' in result.stderr
