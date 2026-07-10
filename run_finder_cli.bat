@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if "%~1"=="" goto usage
if "%~2"=="" goto usage
if "%~3"=="" goto usage

set "SCI_PYTHON_EXE=%LocalAppData%\Sci\env\Scripts\python.exe"
set "SCI_APP_ROOT=%LocalAppData%\Sci\apps\ir_raman_analysis_toolkit"
set "PYTHON_EXE="
if exist "%SCI_PYTHON_EXE%" set "PYTHON_EXE=%SCI_PYTHON_EXE%"
if "%PYTHON_EXE%"=="" (
    call "%CD%\toolkit\setup_sci_env.bat"
    if errorlevel 1 exit /b 1
)
if "%PYTHON_EXE%"=="" if exist "%SCI_PYTHON_EXE%" set "PYTHON_EXE=%SCI_PYTHON_EXE%"

set "IR_RAMAN_DATA_DIR=%SCI_APP_ROOT%\data"
set "IR_RAMAN_PHASE_FINDER_CACHE_DIR=%SCI_APP_ROOT%\data\cache"
set "MPLCONFIGDIR=%SCI_APP_ROOT%\matplotlib"
set "PYTHONPATH=%CD%\Vibrational_Finder;%PYTHONPATH%"
call "%PYTHON_EXE%" -m vibrational_finder.apps.finder_cli --experiment "%~1" --kind "%~2" --library "%~3"
endlocal
exit /b %ERRORLEVEL%

:usage
echo Usage:
echo   run_finder_cli.bat "spectrum.xy" raman "library.csv"
echo   run_finder_cli.bat "spectrum.xy" ftir "library.csv"
endlocal
exit /b 1
