@echo off
echo.
echo  Move For Review -- Apply
echo  ========================
echo.
echo  Step 1: Select the acoustid fingerprint CSV report...
echo.

for /f "delims=" %%i in ('powershell -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms; $w=New-Object System.Windows.Forms.Form; $w.TopMost=$true; $d=New-Object System.Windows.Forms.OpenFileDialog; $d.Title='Select acoustid CSV'; $d.Filter='CSV files (*.csv)|*.csv'; if($d.ShowDialog($w) -eq 'OK'){$d.FileName}"') do set "CSV_PATH=%%i"

if not defined CSV_PATH (
    echo  No file selected. Exiting.
    pause
    exit /b
)
echo  CSV: %CSV_PATH%
echo.
echo  Step 2: Select the SOURCE folder (your organized music folder)...
echo.

for /f "delims=" %%i in ('powershell -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms; $w=New-Object System.Windows.Forms.Form; $w.TopMost=$true; $d=New-Object System.Windows.Forms.FolderBrowserDialog; $d.Description='Select SOURCE folder'; $d.SelectedPath='E:\'; if($d.ShowDialog($w) -eq 'OK'){$d.SelectedPath}"') do set "SOURCE_DIR=%%i"

if not defined SOURCE_DIR (
    echo  No folder selected. Exiting.
    pause
    exit /b
)
echo  Source: %SOURCE_DIR%
echo.
echo  Step 3: Select the DESTINATION folder (where albums will be moved for review)...
echo.

for /f "delims=" %%i in ('powershell -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms; $w=New-Object System.Windows.Forms.Form; $w.TopMost=$true; $d=New-Object System.Windows.Forms.FolderBrowserDialog; $d.Description='Select DESTINATION folder'; $d.SelectedPath='E:\'; if($d.ShowDialog($w) -eq 'OK'){$d.SelectedPath}"') do set "DEST_DIR=%%i"

if not defined DEST_DIR (
    echo  No folder selected. Exiting.
    pause
    exit /b
)
echo  Dest: %DEST_DIR%
echo.

python "%~dp0move_for_review.py" --csv "%CSV_PATH%" --source "%SOURCE_DIR%" --dest "%DEST_DIR%" --apply
pause
