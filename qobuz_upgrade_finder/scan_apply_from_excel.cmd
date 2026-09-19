@echo off
REM Qobuz Upgrade Finder — APPLY with quality preferences from edited Excel
REM
REM Workflow:
REM   1. Run scan_dry_run.cmd first to generate the Excel report
REM   2. Open the Excel, edit the "Download Quality" column as needed
REM   3. Run THIS launcher — pick your edited Excel, then pick your library
REM   4. Two rip-command files are generated:
REM        rip_lossless_*.txt  (FLAC 16-bit, --quality 2)
REM        rip_320_*.txt       (320 kbps MP3, --quality 1)

echo.
echo  Qobuz Upgrade Finder — Apply with Quality Preferences
echo  ======================================================
echo.
echo  Step 1: Select your edited Excel report...
echo.

REM Use PowerShell to open a file picker for the Excel file
for /f "delims=" %%i in ('powershell -NoProfile -Command ^
  "Add-Type -AssemblyName System.Windows.Forms; ^
   $d = New-Object System.Windows.Forms.OpenFileDialog; ^
   $d.Title = 'Select edited Qobuz upgrade report Excel'; ^
   $d.Filter = 'Excel files (*.xlsx)|*.xlsx'; ^
   $d.InitialDirectory = '%~dp0reports'; ^
   if ($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { $d.FileName }"') do set EXCEL_PATH=%%i

if "%EXCEL_PATH%"=="" (
    echo  No Excel file selected. Exiting.
    pause
    exit /b
)

echo  Selected: %EXCEL_PATH%
echo.
echo  Step 2: Select your music library folder...
echo.

python "%~dp0qobuz_upgrade_finder.py" --pick --apply --from-excel "%EXCEL_PATH%"
pause
