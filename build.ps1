$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    throw 'Run setup.ps1 -Dev first.'
}
& '.\.venv\Scripts\python.exe' -m PyInstaller --noconfirm --clean --onedir --windowed `
    --name DiskCleanerStudio --paths src --icon 'src\disk_cleaner_studio\qml\assets\icon.ico' `
    --add-data 'src\disk_cleaner_studio\qml;disk_cleaner_studio/qml' `
    --add-data 'examples\demo.csv;disk_cleaner_studio/resources' `
    --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtPdf `
    run.py
if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }
& '.\.venv\Scripts\python.exe' tools\collect_notices.py
if ($LASTEXITCODE -ne 0) { throw 'Collecting third-party notices failed.' }
Write-Host 'Built: dist\DiskCleanerStudio\DiskCleanerStudio.exe (keep the entire directory)'
