"""Synthetic stored-answer protocol, sharing the restrictive transport contract."""
from pathlib import Path
import runpy
import sys

sys.argv = [__file__, 'storage']
runpy.run_path(str(Path(__file__).with_name('codex_protocol_fixture.py')), run_name='__main__')
