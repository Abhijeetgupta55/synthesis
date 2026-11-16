# Live demo: real pytest runs of NetworkX, default order vs smartci, for one bug (or your own edit).
#
#   scripts\run_live_compare.ps1                      # print a short numbered list of bugs (seeded) and stop
#   scripts\run_live_compare.ps1 -Pick 3              # run bug 3 of that list: default lane, then smartci lane
#   scripts\run_live_compare.ps1 -Edit                # use your own uncommitted edit in external\networkx
#   scripts\run_live_compare.ps1 -Pick 3 -Subset ""   # full suite instead of the subset
#
# -Subset limits collection to one folder of the suite (both lanes get the same path, so the comparison is fair).
# The default is the variant recommended in reports\DEMO_SCRIPT.md. -Mode side-by-side runs both lanes at once
# (for show only: they share the CPU). Timings are only meaningful on mains power.
param(
    [int]$Pick = 0,
    [switch]$Edit,
    [string]$Subset = "networkx/algorithms",
    [int]$Seed = 1,
    [string]$Repo = "external\networkx",
    [string]$Mode = "sequential"
)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$repoDir = Join-Path $root $Repo
$py = Join-Path $root ".venv\Scripts\python.exe"
$sc = Join-Path $repoDir ".venv\Scripts\smartci.exe"
$pickArgs = @("$root\live_demo\pick_bug.py", "--repo", $repoDir, "--seed", $Seed)
if ($Subset) { $pickArgs += @("--subset", $Subset) }

if (-not $Edit -and $Pick -le 0) {
    & $py @pickArgs
    exit 0
}
$battery = (Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue).BatteryStatus
if ($battery -eq 1) { Write-Warning "Laptop is on battery: Windows throttles the CPU, so both lanes run slower than profiled." }

if ($Edit) {
    $bug = "working-tree"
    Push-Location $repoDir
    $changed = git diff --name-only HEAD
    Pop-Location
    if (-not $changed) { Write-Error "No uncommitted change in $Repo. Edit a NetworkX source file first." }
    Write-Host "Your change: $($changed -join ', ')"
} else {
    $bug = (& $py @pickArgs --pick $Pick).Trim()
    Write-Host "Bug $Pick of the list: $bug"
}
$extra = @()
if ($Subset) { $extra = @("--", $Subset) }
Set-Location $repoDir
$sw = [System.Diagnostics.Stopwatch]::StartNew()
& $sc compare --bug $bug --mode $Mode @extra
Write-Host ("whole command: {0:N1} s (both lanes, including pytest start-up and collection)" -f $sw.Elapsed.TotalSeconds)
