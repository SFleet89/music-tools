@echo off
cd /d "%~dp0"
echo.
echo  ============================================================
echo   Rename to CatNo  ^|  APPLY - folders will be renamed
echo  ============================================================
echo.
python rename_to_catno.py --apply
echo.
pause
