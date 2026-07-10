@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "APP_ROOT=%CD%"
set "SCI_ROOT=%LocalAppData%\Sci"
set "SCI_APP_ROOT=%SCI_ROOT%\apps\ir_raman_analysis_toolkit"
set "SCI_PYTHON_EXE=%LocalAppData%\Sci\env\Scripts\python.exe"
set "PYTHON_EXE="
set "LOG_DIR=%SCI_ROOT%\logs\ir_raman_analysis_toolkit"
set "LOG_FILE=%LOG_DIR%\ir_raman_phase_finder_console.log"

if exist "%SCI_PYTHON_EXE%" (
    "%SCI_PYTHON_EXE%" -c "import PySide6, numpy, scipy, pyqtgraph" >nul 2>nul
    if not errorlevel 1 set "PYTHON_EXE=%SCI_PYTHON_EXE%"
)

if "%PYTHON_EXE%"=="" (
    echo Sci environment was not found. Creating/updating shared Sci runtime...
    call "%APP_ROOT%\toolkit\setup_sci_env.bat"
    if errorlevel 1 (
        echo IR/Raman Phase Finder environment setup failed.
        pause
        exit /b 1
    )
)

if "%PYTHON_EXE%"=="" if exist "%SCI_PYTHON_EXE%" set "PYTHON_EXE=%SCI_PYTHON_EXE%"

if "%PYTHON_EXE%"=="" (
    echo Python executable was not found:
    echo %SCI_PYTHON_EXE%
    pause
    exit /b 1
)

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
if not exist "%SCI_APP_ROOT%\data" mkdir "%SCI_APP_ROOT%\data"
if not exist "%SCI_APP_ROOT%\matplotlib" mkdir "%SCI_APP_ROOT%\matplotlib"
if not exist "%SCI_APP_ROOT%\settings" mkdir "%SCI_APP_ROOT%\settings"
set "PYTHONDONTWRITEBYTECODE=1"
set "QT_OPENGL=software"
set "QT_QUICK_BACKEND=software"
set "QT_ANGLE_PLATFORM=warp"
set "IR_RAMAN_DATA_DIR=%SCI_APP_ROOT%\data"
set "IR_RAMAN_PHASE_FINDER_CACHE_DIR=%SCI_APP_ROOT%\data\cache"
set "MPLCONFIGDIR=%SCI_APP_ROOT%\matplotlib"
set "PYTHONPATH=%APP_ROOT%\Vibrational_Finder;%PYTHONPATH%"

echo Starting IR/Raman Phase Finder with console diagnostics...
echo Log file: %LOG_FILE%
echo [%date% %time%] Starting IR/Raman Phase Finder > "%LOG_FILE%"
call "%PYTHON_EXE%" -m vibrational_finder.apps.finder_gui %* 1>> "%LOG_FILE%" 2>&1
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
    echo.
    echo IR/Raman Phase Finder exited with code %EXIT_CODE%.
    echo Last log lines:
    powershell -NoProfile -ExecutionPolicy Bypass -Command "if (Test-Path '%LOG_FILE%') { Get-Content -LiteralPath '%LOG_FILE%' -Tail 30 }"
    pause
)
endlocal & exit /b %EXIT_CODE%
