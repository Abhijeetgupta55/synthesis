#!/usr/bin/env bash
# Live demo (Linux/macOS twin of run_live_compare.ps1): real pytest runs of NetworkX, default order vs smartci.
#   scripts/run_live_compare.sh                 # numbered list of bugs (seed 1)
#   scripts/run_live_compare.sh 3               # run bug 3 of that list
#   scripts/run_live_compare.sh edit            # your own uncommitted edit in external/networkx
# Env: SUBSET (default networkx/algorithms; empty = full suite), SEED (default 1), MODE (sequential|side-by-side)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$ROOT/external/networkx"
SUBSET="${SUBSET-networkx/algorithms}"
PICK=(python "$ROOT/live_demo/pick_bug.py" --repo "$REPO" --seed "${SEED:-1}")
[ -n "$SUBSET" ] && PICK+=(--subset "$SUBSET")
if [ $# -eq 0 ]; then "${PICK[@]}"; exit 0; fi
if [ "$1" = "edit" ]; then BUG=working-tree; else BUG="$("${PICK[@]}" --pick "$1")"; fi
EXTRA=(); [ -n "$SUBSET" ] && EXTRA=(-- "$SUBSET")
cd "$REPO"
time .venv/bin/smartci compare --bug "$BUG" --mode "${MODE:-sequential}" "${EXTRA[@]}"
