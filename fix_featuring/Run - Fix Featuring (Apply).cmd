@echo off
cd /d "%~dp0"
echo.
echo  ============================================================
echo   Fix Featuring Tags  ^|  APPLY - tags will be written
echo  ============================================================
echo.
python fix_featuring.py --apply
echo.
pause
