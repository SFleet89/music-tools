@echo off
cd /d "%~dp0"
echo.
echo  ============================================================
echo   FLAC to CUE  ^|  Generate CUE sheet from MusicBrainz data
echo  ============================================================
echo.
echo  Options:
echo    1. Scan music library automatically (finds all FLAC files
echo       without an existing .cue)
echo    2. Pick a specific file or folder
echo.
set /p choice="  Enter 1 or 2: "
echo.

if "%choice%"=="1" (
    python flac_to_cue.py --scan
) else (
    python flac_to_cue.py
)

echo.
pause
