@echo off
cd /d "%~dp0"
python organize_spotify.py --pick-source --pick-dest
pause
