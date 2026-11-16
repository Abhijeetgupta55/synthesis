#!/usr/bin/env bash
# Starts the dashboard on http://localhost:${PORT:-8501} (no internet needed).
cd "$(dirname "$0")/.."
.venv-demo/bin/python -m streamlit run app/demo.py --server.headless true --browser.gatherUsageStats false --server.port "${PORT:-8501}"
