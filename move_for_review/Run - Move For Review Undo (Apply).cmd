@echo off
echo.
echo  Move For Review Undo -- Apply
echo  ==============================
echo.
echo  Select the move_for_review_applied CSV to undo...
echo.

for /f "delims=" %%i in ('powershell -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms; $w=New-Object System.Windows.Forms.Form; $w.TopMost=$true; $d=New-Object System.Windows.Forms.OpenFileDialog; $d.Title='Select move_for_review_applied CSV'; $d.Filter='CSV files (*.csv)|*.csv'; $d.InitialDirectory='%~dp0reports'; if($d.ShowDialog($w) -eq 'OK'){$d.FileName}"') do set "CSV_PATH=%%i"

if not defined CSV_PATH (
    echo  No file selected. Exiting.
    pause
    exit /b
)
echo  CSV: %CSV_PATH%
echo.

python "%~dp0move_for_review.py" --undo --csv "%CSV_PATH%" --apply
pause
