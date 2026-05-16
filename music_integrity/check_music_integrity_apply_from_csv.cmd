@echo off
echo Music Integrity Checker — APPLY FROM CSV
echo A file picker will open to select your dry-run CSV report.
echo Only files marked 'vbr_needs_fix' or 'error' will be processed.
echo VBR headers will be repaired in place.
echo.
python "%~dp0check_music_integrity.py" --from-csv
echo.
pause
