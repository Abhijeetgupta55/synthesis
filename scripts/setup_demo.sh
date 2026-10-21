#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv-demo
.venv-demo/bin/python -m pip install -r requirements-demo.txt
.venv-demo/bin/python -m pip install -e . --no-deps
echo "Demo environment ready. Run scripts/run_demo.sh"
