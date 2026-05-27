@echo off
cd /d "%~dp0"
echo.
echo  ============================================================
echo   Rename Undo  ^|  DRY RUN - no changes will be made
echo  ============================================================
echo.
python rename_undo.py
echo.
pause
