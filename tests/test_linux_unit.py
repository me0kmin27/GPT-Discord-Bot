from pathlib import Path
import shutil
import subprocess
import pytest
from helperbot.manage import Paths, unit_text


@pytest.mark.skipif(shutil.which('systemd-analyze') is None, reason='systemd parser not installed on this host')
def test_generated_unit_is_accepted_by_real_systemd_parser(tmp_path):
    data=tmp_path/'data'
    data.mkdir()
    unit=tmp_path/'discord-helper.service'
    unit.write_text(unit_text(Paths(tmp_path/'config',data,tmp_path)))
    result=subprocess.run(['systemd-analyze','verify',str(unit)],text=True,capture_output=True)
    assert result.returncode==0,result.stderr
