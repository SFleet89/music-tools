@echo off
cd /d "%~dp0"
echo.
echo  ============================================================
echo   Fix Featuring Tags  ^|  DRY RUN — no changes will be made
echo  ============================================================
echo.
python fix_featuring.py
echo.
pause
