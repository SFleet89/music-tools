@echo off
REM Qobuz Upgrade Finder — DRY RUN (local scan only, no API calls)
python "%~dp0qobuz_upgrade_finder.py" --pick
pause
