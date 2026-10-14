import importlib.util
import json
import os
from pathlib import Path
import pytest


def management():
    assert importlib.util.find_spec('helperbot.manage'), 'Linux management CLI missing'
    from helperbot import manage
    return manage


def test_setup_is_private_idempotent_and_does_not_overwrite_credentials(tmp_path):
    m = management()
    paths = m.Paths(tmp_path/'config', tmp_path/'data', tmp_path/'units')
    m.setup(paths, token='unit-test-not-a-real-token')
    assert (paths.config/'credentials.json').stat().st_mode & 0o777 == 0o600
    assert paths.config.stat().st_mode & 0o777 == 0o700
    m.setup(paths, token='replacement-must-not-win')
    assert json.loads((paths.config/'credentials.json').read_text())['DISCORD_BOT_TOKEN'] == 'unit-test-not-a-real-token'
    assert m.load_token(paths) == 'unit-test-not-a-real-token'


def test_setup_rejects_symlink_and_multiline_token(tmp_path):
    m = management()
    outside = tmp_path/'outside'
    outside.mkdir()
    link = tmp_path/'link'
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(m.ManagementError):
        m.setup(m.Paths(link,tmp_path/'data',tmp_path/'units'),token='test')
    with pytest.raises(m.ManagementError):
        m.setup(m.Paths(tmp_path/'cfg',tmp_path/'data',tmp_path/'units'),token='line\nbreak')


def test_token_loading_rejects_world_readable_file_without_echoing_content(tmp_path):
    m=management()
    paths=m.Paths(tmp_path/'config',tmp_path/'data',tmp_path/'units')
    m.setup(paths,token='unit-test-not-a-real-token')
    (paths.config/'credentials.json').chmod(0o644)
    with pytest.raises(m.ManagementError) as error:
        m.load_token(paths)
    assert 'unit-test' not in str(error.value)
