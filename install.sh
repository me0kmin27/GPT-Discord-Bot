#!/usr/bin/env bash
# Run from a reviewed local checkout, never curl | bash.
set -euo pipefail
if ! command -v python3 >/dev/null 2>&1; then
  printf '%s\n' 'Python 3.9+ with venv/pip is required; install with your OS package manager.' >&2
  exit 2
fi
here=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec python3 "$here/helperbot/bootstrap.py" "$@"
