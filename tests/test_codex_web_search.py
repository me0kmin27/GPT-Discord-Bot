"""Offline pinned-protocol web search tests; never authenticated inference."""
import json
from pathlib import Path
import sys

import pytest
from helperbot import codex_transport as transport, provider


def nested(flat):
    result = {}
    for key, value in flat.items():
        dest = result
        parts = key.split('.')
        for part in parts[:-1]:
            dest = dest.setdefault(part, {})
        dest[parts[-1]] = value
    return result


def test_explicit_search_configuration_preserves_local_restrictions(tmp_path):
    options = {'web_search': 'live', 'model': 'operator-model', 'model_reasoning_effort': 'low'}
    adapter = transport.CodexOAuthProvider(Path(sys.executable), tmp_path, options=options)
    config = transport.execution_config(options)
    assert config['web_search'] == 'live'
    assert config['model'] == 'operator-model'
    assert config['model_reasoning_effort'] == 'low'
    assert config['sandbox_mode'] == 'read-only'
    assert config['approval_policy'] == 'never'
    assert config['features.shell_tool'] is False
    assert config['features.browser_use'] is False
    assert config['mcp_servers'] == {}
    assert 'web_search="live"' in adapter._command()
    transport.validate_config(nested(config), options)
    with pytest.raises(provider.ProviderUnavailable):
        transport.validate_config(nested(config))
    assert transport.execution_config()['web_search'] == 'disabled'


@pytest.mark.parametrize('options', [[], {'shell_tool': True}, {'web_search': True},
    {'web_search': 'cached'}, {'model': ''}, {'model': 'x\ny'},
    {'model_reasoning_effort': False}, {'model': 'x' * 129}])
def test_operator_options_are_narrow_and_validated(options, tmp_path):
    with pytest.raises(ValueError):
        transport.CodexOAuthProvider(Path(sys.executable), tmp_path, options=options)
