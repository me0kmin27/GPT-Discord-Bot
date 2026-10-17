"""Current 60/240 policy boundaries; no network or live inference."""
import pytest

from helperbot import codex_transport as transport


def test_stdio_default_and_maximum_generation_budget(tmp_path):
    client = transport.StdioClient((), cwd=tmp_path, env={})
    assert client.timeout == 240
    assert transport.StdioClient((), cwd=tmp_path, env={}, timeout=240).timeout == 240


@pytest.mark.parametrize('key,argument,maximum', [
    ('setup_timeout_seconds', 'setup_timeout', 60),
    ('generation_timeout_seconds', 'timeout', 240),
])
def test_shared_policy_accepts_boundary_and_fraction(tmp_path, key, argument, maximum):
    for value in (0.5, maximum - 0.5, maximum):
        options = {key: value}
        assert transport.validate_options(options) == options
        provider = transport.CodexOAuthProvider('/synthetic/codex', tmp_path, options=options)
        assert getattr(provider, argument) == value
        provider = transport.CodexOAuthProvider('/synthetic/codex', tmp_path, **{argument: value})
        assert getattr(provider, argument) == value


@pytest.mark.parametrize('key,argument,maximum', [
    ('setup_timeout_seconds', 'setup_timeout', 60),
    ('generation_timeout_seconds', 'timeout', 240),
])
@pytest.mark.parametrize('invalid', [None, True, False, '60', 0, -1, float('nan'),
                                     float('inf'), float('-inf'), 'above_maximum'])
def test_shared_policy_rejects_invalid_values(tmp_path, key, argument, maximum, invalid):
    value = maximum + 0.01 if invalid == 'above_maximum' else invalid
    with pytest.raises(ValueError):
        transport.validate_options({key: value})
    with pytest.raises(ValueError):
        transport.CodexOAuthProvider('/synthetic/codex', tmp_path, **{argument: value})
    with pytest.raises(ValueError):
        transport.CodexOAuthProvider('/synthetic/codex', tmp_path, options={key: value})
    if argument == 'timeout':
        with pytest.raises(ValueError):
            transport.StdioClient((), cwd=tmp_path, env={}, timeout=value)
