@echo off
echo Music Integrity Checker — DRY RUN with FULL DECODE CHECK
echo Folder picker will open. This will be slow (2-5 seconds per file).
echo No files will be modified.
echo.
python "%~dp0check_music_integrity.py" --integrity
echo.
pause
