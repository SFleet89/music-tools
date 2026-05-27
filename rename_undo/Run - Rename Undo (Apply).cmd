@echo off
cd /d "%~dp0"
echo.
echo  ============================================================
echo   Rename Undo  ^|  APPLY - renames will be reversed
echo  ============================================================
echo.
python rename_undo.py --apply
echo.
pause
