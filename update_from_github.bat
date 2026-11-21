@echo off
setlocal
cd /d "%~dp0"

echo Updating IR/Raman Phase Finder from GitHub...

if not exist ".git" (
    echo This folder is not a Git checkout.
    echo Clone or download the repository, then run this script from the project root.
    pause
    exit /b 1
)

where git >nul 2>nul
if errorlevel 1 (
    echo Git was not found.
    where winget >nul 2>nul
    if errorlevel 1 (
        echo Install Git from https://git-scm.com/download/win and run this script again.
        pause
        exit /b 1
    )
    echo.
    set /p INSTALL_GIT=Install Git with winget now? [Y/N]:
    if /I not "%INSTALL_GIT%"=="Y" exit /b 1
    winget install --id Git.Git -e --source winget
    if errorlevel 1 (
        echo Git installation failed.
        pause
        exit /b 1
    )
)

git --version >nul 2>nul
if errorlevel 1 (
    echo Git is installed but cannot be launched from this window.
    echo Open a new Command Prompt and run update_from_github.bat again.
    pause
    exit /b 1
)

git fetch origin
if errorlevel 1 goto failed

git pull --ff-only origin main
if errorlevel 1 (
    echo.
    echo Update could not be applied automatically.
    echo Local source files may have changed, or the Git history is not a fast-forward.
    pause
    exit /b 1
)

echo.
echo Updating Python environment after GitHub update...
call toolkit\setup_sci_env.bat
if errorlevel 1 goto failed

echo.
echo Update complete.
pause
exit /b 0

:failed
echo.
echo Update failed.
pause
exit /b 1
