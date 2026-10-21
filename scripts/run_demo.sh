#!/usr/bin/env bash
cd "$(dirname "$0")/.."
.venv-demo/bin/python -m streamlit run app/demo.py --server.headless true --browser.gatherUsageStats false
