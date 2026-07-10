@echo off
setlocal
cd /d "%~dp0"
call clean_payload.bat
if not exist output mkdir output
del /q "output\IR_Raman_Phase_Finder_Setup_*.exe" >nul 2>nul
del /q "output\IR_Raman_analysis_Toolkit_Setup_*.exe" >nul 2>nul

set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if not defined ISCC (
    echo Inno Setup 6 compiler was not found.
    echo Install it from https://jrsoftware.org/isinfo.php
    exit /b 1
)

"%ISCC%" IR_Raman_Phase_Finder.iss
if errorlevel 1 exit /b 1

echo Installer was created in installer\output.
exit /b 0
