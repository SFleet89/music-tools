@echo off
cd /d "%~dp0"
echo Installing Music Tools dependencies...
pip install PySide6 mutagen musicbrainzngs
echo.
echo Done. You can now run the Music Tools GUI.
pause
