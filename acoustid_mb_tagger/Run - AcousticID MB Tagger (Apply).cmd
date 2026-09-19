@echo off
cd /d "%~dp0"
python acoustid_mb_tagger.py --pick --apply
pause
