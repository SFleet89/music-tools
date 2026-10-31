@echo off
cd /d "%~dp0"
echo Installing Music Tools dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo Install FAILED. Read the messages above.
    pause
    exit /b 1
)
echo.
echo Done. You can now run the Music Tools GUI.
pause
