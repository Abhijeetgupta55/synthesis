# Creates .venv-demo with the pinned demo dependencies. Works offline once the wheels are cached.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
python -m venv .venv-demo
.\.venv-demo\Scripts\python -m pip install -r requirements-demo.txt
.\.venv-demo\Scripts\python -m pip install -e . --no-deps
Write-Host "Demo environment ready. Run scripts\run_demo.ps1"
