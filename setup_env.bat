@echo off
setlocal
cd /d "%~dp0"
call "%~dp0toolkit\setup_sci_env.bat" %*
endlocal
exit /b %ERRORLEVEL%
