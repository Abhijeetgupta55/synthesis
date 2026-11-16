# Starts the dashboard on http://localhost:8501 (no internet needed). Use -Port if 8501 is taken.
param([int]$Port = 8501)
Set-Location (Split-Path $PSScriptRoot -Parent)
.\.venv-demo\Scripts\python -m streamlit run app\demo.py --server.headless true --browser.gatherUsageStats false --server.port $Port
