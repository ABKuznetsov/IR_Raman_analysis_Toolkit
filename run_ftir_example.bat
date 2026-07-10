@echo off
setlocal EnableExtensions
cd /d "%~dp0"

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
call "%PYTHON_EXE%" -m vibrational_finder.apps.ftir_cli --experiment examples\observed_ftir.xy --library examples\library.csv
pause
endlocal
exit /b %ERRORLEVEL%
