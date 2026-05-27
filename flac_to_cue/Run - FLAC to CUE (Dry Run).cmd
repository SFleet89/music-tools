@echo off
cd /d "%~dp0"
echo.
echo  ============================================================
echo   Audio to CUE  v2.0  ^|  DRY RUN
echo   Scans for audio files and resolves MB matches.
echo   No .cue files will be written.
echo  ============================================================
echo.
python flac_to_cue.py
echo.
pause
