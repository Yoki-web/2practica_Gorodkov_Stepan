@echo off
setlocal
cd /d "%~dp0"
if defined PYTHON (
  "%PYTHON%" -B -m src %*
) else (
  python -B -m src %*
)
exit /b %errorlevel%
