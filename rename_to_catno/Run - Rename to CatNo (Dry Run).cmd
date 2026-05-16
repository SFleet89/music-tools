@echo off
cd /d "%~dp0"
echo.
echo  ============================================================
echo   Rename to CatNo  ^|  DRY RUN — no changes will be made
echo  ============================================================
echo.
python rename_to_catno.py
echo.
pause
