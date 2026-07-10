@echo off
setlocal
set "ROOT=%~dp0.."
echo Cleaning Python cache files from payload...
for /d /r "%ROOT%" %%D in (__pycache__) do (
    if exist "%%D" rmdir /s /q "%%D"
)
del /s /q "%ROOT%\*.pyc" >nul 2>nul
del /s /q "%ROOT%\*.pyo" >nul 2>nul
echo Done.
