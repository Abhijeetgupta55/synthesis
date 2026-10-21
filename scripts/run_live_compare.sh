#!/usr/bin/env bash
# Usage: scripts/run_live_compare.sh external/networkx <fix-sha-or-mutant-id> [sequential|side-by-side]
set -euo pipefail
cd "$(dirname "$0")/../$1"
.venv/bin/smartci compare --bug "$2" --mode "${3:-sequential}"
