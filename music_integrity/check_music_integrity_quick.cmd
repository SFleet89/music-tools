@echo off
echo Music Integrity Checker - DRY RUN (VBR check only, fast)
echo Folder picker will open. No files will be modified.
echo NOTE: Full decode check is skipped. Use the standard dry run for a deeper scan.
echo.
python "%~dp0check_music_integrity.py" --quick
echo.
pause
