$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$projectPython = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
& $projectPython -m pip install --upgrade pip-tools
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $projectPython -m piptools compile --strip-extras --upgrade --output-file requirements.txt requirements.in
exit $LASTEXITCODE
