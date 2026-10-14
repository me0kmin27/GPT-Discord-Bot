"""Pure tests for the credential-free binary probe; no installed CLI required."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('probe_codex', Path(__file__).with_name('probe_codex.py'))
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def test_native_binary_resolution_never_uses_global_path(tmp_path):
    executable = tmp_path / '@openai/codex-platform/vendor/target/bin/codex'
    executable.parent.mkdir(parents=True)
    executable.touch()
    assert probe.resolve_executable(tmp_path) == executable
    assert probe.resolve_executable(executable) == executable
    second = tmp_path / '@openai/codex-other/vendor/target/bin/codex'
    second.parent.mkdir(parents=True)
    second.touch()
    with pytest.raises(ValueError):
        probe.resolve_executable(tmp_path)


def test_native_binary_resolution_rejects_missing_binary(tmp_path):
    with pytest.raises(ValueError):
        probe.resolve_executable(tmp_path)
