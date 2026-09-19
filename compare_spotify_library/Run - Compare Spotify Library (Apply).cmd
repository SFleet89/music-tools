@echo off
cd /d "%~dp0"
python compare_spotify_library.py --pick-spotify --pick-library
pause
