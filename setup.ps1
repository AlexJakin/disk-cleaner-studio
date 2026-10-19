param([string]$Python = "", [switch]$Dev)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    if ($Python) {
        & $Python -m venv .venv
    } elseif (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv .venv
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv .venv
    } else {
        throw 'Python 3.11+ is required. Install Python, or run setup.ps1 -Python C:\path\python.exe'
    }
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create virtual environment.' }
}
$requirements = if ($Dev) { 'requirements-dev.txt' } else { 'requirements.txt' }
& '.\.venv\Scripts\python.exe' -m pip install -r $requirements
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
Write-Host 'Ready. Double-click Start.cmd or run .\.venv\Scripts\python.exe run.py'
