@echo off
setlocal

set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" (
    set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
) else if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" (
    set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
) else if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" (
    set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
)

if defined ISCC (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_installer.ps1" -InnoCompiler "%ISCC%" %*
) else (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_installer.ps1" %*
)
