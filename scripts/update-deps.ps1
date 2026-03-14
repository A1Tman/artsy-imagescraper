$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

python -m pip install --upgrade pip-tools
python -m piptools compile --strip-extras --upgrade --output-file requirements.txt requirements.in
