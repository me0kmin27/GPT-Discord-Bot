"""Explicit local selection, no credentials or live inference."""
import sys
from pathlib import Path
import pytest
from helperbot.provider import Request, ProviderUnavailable
from helperbot.codex_transport import CodexOAuthProvider


def test_fixed_execution_controls(tmp_path):
    command = CodexOAuthProvider(Path(sys.executable), tmp_path)._command()
    values = dict(command[i + 1].split('=', 1) for i, v in enumerate(command) if v == '-c')
    assert values['sandbox_mode'] == '"read-only"'
    assert values['approval_policy'] == '"never"'
    assert values['web_search'] == '"disabled"'
    assert values['features.shell_tool'] == 'false'
    assert values['features.code_mode'] == 'false'
    assert values['features.view_image'] == 'false'
    assert values['shell_environment_policy.inherit'] == '"none"'
    assert not any('bypass' in arg for arg in command)


def test_effective_config_must_match_restrictions():
    from helperbot.codex_transport import execution_config, validate_config
    config = {}
    for key, value in execution_config().items():
        if key.startswith('tools.'):
            continue  # Official config/read omits utility tool switches.
        node = config
        parts = key.split('.')
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
    validate_config(config)
    config['features']['shell_tool'] = True
    with pytest.raises(ProviderUnavailable, match='configuration'):
        validate_config(config)
    config['features']['shell_tool'] = False
    config['mcp_servers'] = {'injected': {'command': 'false'}}
    with pytest.raises(ProviderUnavailable, match='configuration'):
        validate_config(config)


def test_selection_is_explicit(tmp_path):
    from helperbot.provider import build_provider, DisabledCodex
    assert isinstance(build_provider('disabled-codex'), DisabledCodex)
    actual = build_provider('codex-oauth', data=tmp_path, executable=Path(sys.executable))
    assert isinstance(actual, CodexOAuthProvider)
    with pytest.raises(ValueError):
        build_provider('codex-oauth', data=Path('relative'), executable=Path(sys.executable))
    with pytest.raises(ValueError):
        build_provider('invented')
    with pytest.raises(ValueError):
        build_provider('codex-oauth')


@pytest.mark.parametrize('timeout', [0, -1, True, float('nan'), 241])
def test_invalid_timeout_rejected(tmp_path, timeout):
    with pytest.raises(ValueError):
        CodexOAuthProvider(Path(sys.executable), tmp_path, timeout=timeout)


async def test_operator_config_cannot_inject_tools(tmp_path):
    home = tmp_path / 'codex'
    home.mkdir()
    (home / 'config.toml').write_text('[mcp_servers.never]\ncommand="false"\n')
    with pytest.raises(ProviderUnavailable, match='configuration'):
        await CodexOAuthProvider(Path(sys.executable), tmp_path).answer(Request((1, 2), 'q', (), ()))


async def test_symlink_auth_is_not_followed(tmp_path):
    home = tmp_path / 'codex'
    home.mkdir()
    (home / 'auth.json').symlink_to(tmp_path / 'nonexistent-unrelated-auth')
    with pytest.raises(ProviderUnavailable, match='auth'):
        await CodexOAuthProvider(Path(sys.executable), tmp_path).answer(Request((1, 2), 'q', (), ()))
