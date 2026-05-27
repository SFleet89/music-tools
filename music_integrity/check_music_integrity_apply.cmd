@echo off
echo Music Integrity Checker - APPLY MODE (repairs VBR headers)
echo Folder picker will open. VBR headers will be repaired.
echo.
python "%~dp0check_music_integrity.py" --apply
echo.
pause
