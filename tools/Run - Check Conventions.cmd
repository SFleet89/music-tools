@echo off
cd /d "%~dp0.."
python -B -X utf8 tools\check_conventions.py
echo.
echo Exit code: %ERRORLEVEL%  (0 = pass, 1 = something failed)
pause
