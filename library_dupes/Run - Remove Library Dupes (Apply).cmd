@echo off
cd /d "%~dp0"
python remove_library_dupes.py --apply
pause
