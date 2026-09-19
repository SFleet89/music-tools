@echo off
cd /d "%~dp0"
python shazam_identify.py --pick --skip-tagged
pause
