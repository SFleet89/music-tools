@echo off
echo Fix Featuring Tags - APPLY FROM CSV
echo A file picker will open to select your dry-run CSV report.
echo Only files marked 'pending' in the CSV will be modified.
echo.
python "%~dp0fix_featuring.py" --from-csv
echo.
pause
