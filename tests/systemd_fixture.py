"""Offline process fixture, NOT the Discord bot or a readiness probe."""
import os
from pathlib import Path
import signal
import sys
import time

log = Path(sys.argv[1])

def record(event):
    with log.open('a') as out:
        out.write(f'{event} {os.getpid()}\n')


def stop(signum, frame):
    record('stop')
    raise SystemExit(0)


signal.signal(signal.SIGTERM, stop)
record('start')
while True:
    time.sleep(1)
