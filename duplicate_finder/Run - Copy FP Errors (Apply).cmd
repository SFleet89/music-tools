@echo off
cd /d "%~dp0"
python build_fp_cache.py --fp-only --copy-errors --apply
pause
