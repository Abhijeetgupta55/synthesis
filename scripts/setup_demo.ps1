# Creates .venv-demo with the pinned dashboard dependencies (requirements.txt). Needs Python 3.11+.
# Works offline once the wheels are cached.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
$cands = @(@("py", "-3.11"), @("py", "-3.12"), @("py", "-3.13"), @("python"), @("python3"))
$py = $null
foreach ($c in $cands) {
    try {
        $v = & $c[0] $c[1..9] -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -eq 0 -and [version]$v -ge [version]"3.11") { $py = $c; break }
    } catch { }
}
if (-not $py) { Write-Error "Python 3.11 or newer is needed (python.org or 'winget install Python.Python.3.11')." }
Write-Host "Using $($py -join ' ') (Python $v)"
& $py[0] $py[1..9] -m venv .venv-demo
.\.venv-demo\Scripts\python -m pip install --upgrade pip
.\.venv-demo\Scripts\python -m pip install -r requirements.txt
.\.venv-demo\Scripts\python -m pip install -e . --no-deps
Write-Host "Demo environment ready. Run scripts\run_demo.ps1"
