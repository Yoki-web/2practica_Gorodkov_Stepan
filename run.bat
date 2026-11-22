@echo off
setlocal
cd /d "%~dp0"
if defined PYTHON (
  "%PYTHON%" -B -m src.main %*
) else (
  python -B -m src.main %*
)
exit /b %errorlevel%
