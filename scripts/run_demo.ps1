# Starts the demo on http://localhost:8501 (no internet needed).
Set-Location (Split-Path $PSScriptRoot -Parent)
.\.venv-demo\Scripts\python -m streamlit run app\demo.py --server.headless true --browser.gatherUsageStats false
