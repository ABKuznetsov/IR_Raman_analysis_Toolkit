@echo off
setlocal EnableExtensions
set "APP_ROOT=%~dp0"
for %%I in ("%APP_ROOT%") do set "APP_ROOT=%%~fI"
set "PREVIEW_SCRIPT=%APP_ROOT%\toolkit\launch_ir_raman_phase_finder_preview.ps1"

if not exist "%PREVIEW_SCRIPT%" (
    echo Startup preview script was not found:
    echo %PREVIEW_SCRIPT%
    pause
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File "%PREVIEW_SCRIPT%" -AppId ir_raman_phase_finder
endlocal
exit /b %ERRORLEVEL%
