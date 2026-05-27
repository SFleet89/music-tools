@echo off
cd /d "%~dp0"
echo.
echo  ============================================================
echo   Audio to CUE  v2.0  ^|  APPLY
echo   Resolves MB matches and writes .cue files.
echo   You will be asked to confirm each file before it is written.
echo  ============================================================
echo.
python flac_to_cue.py --apply
echo.
pause
