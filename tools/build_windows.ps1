param(
    [switch]$NoVenv
)

$ErrorActionPreference = "Stop"

# Stay in current folder (tools)
$RepoRoot = Get-Location

if ($NoVenv) {
    $Python = "python"
} else {
    $VenvPath = Join-Path $RepoRoot ".venv-windows"
    $Python = Join-Path $VenvPath "Scripts\python.exe"

    if (-not (Test-Path $Python)) {
        python -m venv $VenvPath
    }
}

# Upgrade pip
& $Python -m pip install --upgrade pip

# Install deps (relative to tools folder)
& $Python -m pip install -r requirements.txt -r requirements-build.txt

# Build
& $Python -m PyInstaller `
    --clean `
    --noconfirm `
    --onefile `
    --windowed `
    --name LocalControl-GUI `
    botctl_gui_desktop.py

Write-Host "Built dist\LocalControl-GUI.exe"
