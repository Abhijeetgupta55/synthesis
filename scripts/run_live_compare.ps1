# Real side-by-side pytest runs for one bug of a repository that smartci has profiled and mined.
# Usage: scripts\run_live_compare.ps1 -Repo external\networkx -Bug <fix-sha-or-mutant-id> [-Mode side-by-side]
param([string]$Repo = "external\networkx", [Parameter(Mandatory = $true)][string]$Bug, [string]$Mode = "sequential")
Set-Location (Join-Path (Split-Path $PSScriptRoot -Parent) $Repo)
.\.venv\Scripts\smartci compare --bug $Bug --mode $Mode
