@echo off
echo Music Integrity Checker - DRY RUN (VBR + full decode check)
echo Folder picker will open. No files will be modified.
echo NOTE: Full decode check is slow - expect 2-5 seconds per file.
echo.
python "%~dp0check_music_integrity.py"
echo.
pause
