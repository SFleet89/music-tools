@echo off
cd /d "%~dp0"
python acoustid_fingerprint.py --pick --apply
pause
