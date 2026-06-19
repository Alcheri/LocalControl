param(
    [string]$InnoCompiler
)

$ErrorActionPreference = "Stop"

$ToolsRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ToolsRoot
$GuiExe = Join-Path $RepoRoot "dist\LocalControl-GUI.exe"
$Script = Join-Path $ToolsRoot "LocalControl-GUI.iss"

if (-not (Test-Path $GuiExe)) {
    throw "Missing $GuiExe. Run tools\build_windows.ps1 and copy the binary to dist first."
}

if (-not $InnoCompiler) {
    $Candidates = @("ISCC.exe")
    $ProgramFilesX86 = ${env:ProgramFiles(x86)}
    if ($ProgramFilesX86) {
        $Candidates += Join-Path $ProgramFilesX86 "Inno Setup 6\ISCC.exe"
    }
    if ($env:ProgramFiles) {
        $Candidates += Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"
    }
    foreach ($Candidate in $Candidates) {
        if (Get-Command $Candidate -ErrorAction SilentlyContinue) {
            $InnoCompiler = $Candidate
            break
        }
    }
}

if (-not $InnoCompiler) {
    throw "Inno Setup compiler not found. Add ISCC.exe to PATH or pass -InnoCompiler."
}

& $InnoCompiler $Script

Write-Host "Built dist\LocalControl-GUI-Setup.exe"
