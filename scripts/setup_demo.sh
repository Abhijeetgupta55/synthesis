#!/usr/bin/env bash
# Creates .venv-demo with the pinned dashboard dependencies (requirements.txt). Needs Python 3.11+.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=""
for c in python3.11 python3.12 python3.13 python3 python; do
  if command -v "$c" >/dev/null && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then PY="$c"; break; fi
done
[ -n "$PY" ] || { echo "Python 3.11 or newer is needed" >&2; exit 1; }
"$PY" -m venv .venv-demo
.venv-demo/bin/python -m pip install --upgrade pip
.venv-demo/bin/python -m pip install -r requirements.txt
.venv-demo/bin/python -m pip install -e . --no-deps
echo "Demo environment ready. Run scripts/run_demo.sh"
