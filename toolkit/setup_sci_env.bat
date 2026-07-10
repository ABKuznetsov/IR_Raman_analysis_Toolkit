@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "APP_ROOT=%~dp0.."
for %%I in ("%APP_ROOT%") do set "APP_ROOT=%%~fI"

set "SCI_ROOT=%LocalAppData%\Sci"
set "ENV_ROOT=%SCI_ROOT%\env"
set "BIN_ROOT=%SCI_ROOT%\bin"
set "APP_DATA_ROOT=%SCI_ROOT%\apps\ir_raman_analysis_toolkit"
set "DATA_ROOT=%APP_DATA_ROOT%\data"
set "MPL_ROOT=%APP_DATA_ROOT%\matplotlib"
set "SETTINGS_ROOT=%APP_DATA_ROOT%\settings"
set "LOG_ROOT=%SCI_ROOT%\logs\ir_raman_analysis_toolkit"
set "DOWNLOAD_ROOT=%SCI_ROOT%\downloads"
set "UPDATE_ROOT=%SCI_ROOT%\updates"
set "LOG_FILE=%LOG_ROOT%\setup.log"

if not exist "%SCI_ROOT%" mkdir "%SCI_ROOT%"
if not exist "%BIN_ROOT%" mkdir "%BIN_ROOT%"
if not exist "%APP_DATA_ROOT%" mkdir "%APP_DATA_ROOT%"
if not exist "%DATA_ROOT%" mkdir "%DATA_ROOT%"
if not exist "%MPL_ROOT%" mkdir "%MPL_ROOT%"
if not exist "%SETTINGS_ROOT%" mkdir "%SETTINGS_ROOT%"
if not exist "%LOG_ROOT%" mkdir "%LOG_ROOT%"
if not exist "%DOWNLOAD_ROOT%" mkdir "%DOWNLOAD_ROOT%"
if not exist "%UPDATE_ROOT%" mkdir "%UPDATE_ROOT%"

echo [%date% %time%] Starting Sci environment setup for IR/Raman Phase Finder > "%LOG_FILE%"
echo Application root: %APP_ROOT%>> "%LOG_FILE%"
echo Sci root: %SCI_ROOT%>> "%LOG_FILE%"
echo Runtime env root: %ENV_ROOT%>> "%LOG_FILE%"
echo IR/Raman app data root: %APP_DATA_ROOT%>> "%LOG_FILE%"

call :check_windows_version
if errorlevel 1 exit /b 1

call :find_python
if errorlevel 1 (
    call :install_python
    if errorlevel 1 (
        echo Python 3.11+ is required. Install Python and run setup again.
        echo Python 3.11+ not found.>> "%LOG_FILE%"
        exit /b 1
    )
    call :find_python
)

if errorlevel 1 (
    echo Python 3.11+ is installed but could not be launched.
    echo Python launch failed after install.>> "%LOG_FILE%"
    exit /b 1
)

echo Using Python: %PYTHON_CMD%
echo Using Python: %PYTHON_CMD%>> "%LOG_FILE%"

if not exist "%ENV_ROOT%\Scripts\python.exe" (
    echo Creating Sci environment...
    echo Creating venv at %ENV_ROOT%>> "%LOG_FILE%"
    %PYTHON_CMD% -m venv "%ENV_ROOT%" >> "%LOG_FILE%" 2>&1
)

if not exist "%ENV_ROOT%\Scripts\python.exe" (
    echo Failed to create Sci environment.
    echo venv creation failed.>> "%LOG_FILE%"
    exit /b 1
)

echo Upgrading pip and build tools...
echo Upgrading pip and build tools...>> "%LOG_FILE%"
call "%ENV_ROOT%\Scripts\python.exe" -m pip install --disable-pip-version-check --timeout 60 --retries 3 --prefer-binary --upgrade pip setuptools wheel >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto failed

echo Installing IR/Raman Phase Finder requirements...
echo Installing IR/Raman Phase Finder requirements...>> "%LOG_FILE%"
call "%ENV_ROOT%\Scripts\python.exe" -m pip install --disable-pip-version-check --timeout 60 --retries 3 --prefer-binary -e "%APP_ROOT%" >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto failed

echo Writing launchers...>> "%LOG_FILE%"
call :write_launchers
echo Updating user PATH...>> "%LOG_FILE%"
call :ensure_user_path "%BIN_ROOT%"

echo [%date% %time%] Sci environment setup complete.>> "%LOG_FILE%"
echo Sci environment is ready.
exit /b 0

:write_launchers
> "%BIN_ROOT%\sci-python.cmd" echo @echo off
>> "%BIN_ROOT%\sci-python.cmd" echo "%ENV_ROOT%\Scripts\python.exe" %%*
> "%BIN_ROOT%\ir-raman-phase-finder.cmd" echo @echo off
>> "%BIN_ROOT%\ir-raman-phase-finder.cmd" echo set "APP_ROOT=%APP_ROOT%"
>> "%BIN_ROOT%\ir-raman-phase-finder.cmd" echo set "SCI_ROOT=%%LocalAppData%%\Sci"
>> "%BIN_ROOT%\ir-raman-phase-finder.cmd" echo set "SCI_APP_ROOT=%%SCI_ROOT%%\apps\ir_raman_analysis_toolkit"
>> "%BIN_ROOT%\ir-raman-phase-finder.cmd" echo set "PYTHONPATH=%%APP_ROOT%%\Vibrational_Finder;%%PYTHONPATH%%"
>> "%BIN_ROOT%\ir-raman-phase-finder.cmd" echo set "IR_RAMAN_DATA_DIR=%%SCI_APP_ROOT%%\data"
>> "%BIN_ROOT%\ir-raman-phase-finder.cmd" echo set "IR_RAMAN_PHASE_FINDER_CACHE_DIR=%%SCI_APP_ROOT%%\data\cache"
>> "%BIN_ROOT%\ir-raman-phase-finder.cmd" echo set "MPLCONFIGDIR=%%SCI_APP_ROOT%%\matplotlib"
>> "%BIN_ROOT%\ir-raman-phase-finder.cmd" echo set "QT_OPENGL=software"
>> "%BIN_ROOT%\ir-raman-phase-finder.cmd" echo set "QT_QUICK_BACKEND=software"
>> "%BIN_ROOT%\ir-raman-phase-finder.cmd" echo set "QT_ANGLE_PLATFORM=warp"
>> "%BIN_ROOT%\ir-raman-phase-finder.cmd" echo set "QT_QPA_PLATFORM=windows"
>> "%BIN_ROOT%\ir-raman-phase-finder.cmd" echo "%ENV_ROOT%\Scripts\python.exe" -m vibrational_finder.apps.finder_gui %%*
> "%BIN_ROOT%\ir-raman.cmd" echo @echo off
>> "%BIN_ROOT%\ir-raman.cmd" echo call "%BIN_ROOT%\ir-raman-phase-finder.cmd" %%*
> "%BIN_ROOT%\ir-raman-analysis-toolkit.cmd" echo @echo off
>> "%BIN_ROOT%\ir-raman-analysis-toolkit.cmd" echo call "%BIN_ROOT%\ir-raman-phase-finder.cmd" %%*
> "%BIN_ROOT%\ir-raman-python.cmd" echo @echo off
>> "%BIN_ROOT%\ir-raman-python.cmd" echo "%ENV_ROOT%\Scripts\python.exe" %%*
exit /b 0

:ensure_user_path
set "BIN_PATH=%~1"
powershell -NoProfile -Command "$bin=[Environment]::ExpandEnvironmentVariables('%BIN_PATH%'); $path=[Environment]::GetEnvironmentVariable('Path','User'); if (-not $path) { $path='' }; $parts=$path -split ';' | Where-Object { $_ }; if ($parts -notcontains $bin) { $new=($parts + $bin) -join ';'; [Environment]::SetEnvironmentVariable('Path',$new,'User') }" >> "%LOG_FILE%" 2>&1
exit /b 0

:check_windows_version
ver | findstr /r /c:" 10\." >nul
if errorlevel 1 (
    echo IR/Raman Phase Finder requires Windows 10 or Windows 11.
    echo Unsupported Windows version.>> "%LOG_FILE%"
    exit /b 1
)
exit /b 0

:find_python
set "PYTHON_CMD="
set "PYTHON_TEST=import sys; raise SystemExit(0 if sys.version_info >= (3, 11) and sys.version_info < (3, 13) else 1)"
if exist "%LocalAppData%\Programs\Python\Python311\python.exe" (
    "%LocalAppData%\Programs\Python\Python311\python.exe" -c "%PYTHON_TEST%" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=""%LocalAppData%\Programs\Python\Python311\python.exe"""& exit /b 0
)
if exist "%ProgramFiles%\Python311\python.exe" (
    "%ProgramFiles%\Python311\python.exe" -c "%PYTHON_TEST%" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=""%ProgramFiles%\Python311\python.exe"""& exit /b 0
)
py -3.11 -c "%PYTHON_TEST%" >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=py -3.11"& exit /b 0
python -c "%PYTHON_TEST%" >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=python"& exit /b 0
exit /b 1

:install_python
where winget >nul 2>nul
if errorlevel 1 goto install_python_direct
echo Python 3.11+ was not found. Installing with winget...
echo Installing Python 3.11 with winget...>> "%LOG_FILE%"
winget install --id Python.Python.3.11 -e --source winget --accept-package-agreements --accept-source-agreements >> "%LOG_FILE%" 2>&1
if not errorlevel 1 exit /b 0

:install_python_direct
set "PYTHON_INSTALLER_DIR=%SCI_ROOT%\downloads"
set "PYTHON_INSTALLER=%PYTHON_INSTALLER_DIR%\python-3.11.9-amd64.exe"
set "PYTHON_URL=https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
if not exist "%PYTHON_INSTALLER_DIR%" mkdir "%PYTHON_INSTALLER_DIR%"
echo Downloading Python 3.11.9 from python.org...>> "%LOG_FILE%"
powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%PYTHON_INSTALLER%'" >> "%LOG_FILE%" 2>&1
if errorlevel 1 exit /b 1
if not exist "%PYTHON_INSTALLER%" exit /b 1
echo Installing Python 3.11.9 for current user...>> "%LOG_FILE%"
"%PYTHON_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=0 Include_launcher=1 Include_pip=1 Include_tcltk=1 Include_test=0 Shortcuts=0 >> "%LOG_FILE%" 2>&1
exit /b %ERRORLEVEL%

:failed
echo IR/Raman Phase Finder setup failed. See log: %LOG_FILE%
echo [%date% %time%] setup failed.>> "%LOG_FILE%"
exit /b 1
