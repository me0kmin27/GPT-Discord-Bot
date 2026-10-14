import json
from helperbot import manage
from test_settings_ops import paths_at


def test_cli_uses_shared_settings_and_preserves_existing_commands(tmp_path, capsys):
    paths = paths_at(tmp_path)
    args = ['--config-dir', str(paths.config), '--data-dir', str(paths.data), '--unit-dir', str(paths.units)]
    assert manage.main(args+['settings', 'show']) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown['values']['web_search'] == 'live'
    assert manage.main(args+['settings', 'set', '--model', 'cli-model', '--revision', shown['revision']]) == 0
    capsys.readouterr()
    assert manage.main(args+['doctor']) == 0
    assert 'provider=codex-oauth' in capsys.readouterr().out
    assert manage.main(args+['gui', '--help']) is None
