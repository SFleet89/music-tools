@echo off
cd /d "%~dp0"
echo ============================================================
echo  Music Tools GUI -- PyInstaller Smoke Test Build
echo  Started: %DATE% %TIME%
echo ============================================================
echo.

set LOG="%~dp0gui\reports\pyinstaller_build_log.txt"
if not exist "%~dp0gui\reports\" mkdir "%~dp0gui\reports\"

echo Checking Python version...
python --version
echo.

echo Checking pip...
python -m pip --version
echo.

echo --- Installing / upgrading PyInstaller ---
python -m pip install --upgrade pyinstaller
echo.

echo --- Checking installed packages ---
python -m pip list | findstr /i "pyside6 mutagen beautifulsoup4 requests pyinstaller"
echo.

echo --- Running PyInstaller build ---
echo Entry point: gui\main.py
echo Output: dist\MusicTools\
echo.

python -m PyInstaller ^
  --name "MusicTools" ^
  --windowed ^
  --noconfirm ^
  --clean ^
  --add-data "gui_config.json;." ^
  --add-data "music_config.json;." ^
  --hidden-import "PySide6.QtCore" ^
  --hidden-import "PySide6.QtGui" ^
  --hidden-import "PySide6.QtWidgets" ^
  --hidden-import "PySide6.QtXml" ^
  --hidden-import "mutagen" ^
  --hidden-import "mutagen.flac" ^
  --hidden-import "mutagen.mp3" ^
  --hidden-import "mutagen.mp4" ^
  --hidden-import "mutagen.oggvorbis" ^
  --hidden-import "mutagen.wave" ^
  --hidden-import "mutagen.aiff" ^
  --hidden-import "mutagen.id3" ^
  --hidden-import "mutagen.apev2" ^
  --hidden-import "mutagen.asf" ^
  --hidden-import "bs4" ^
  --hidden-import "requests" ^
  --hidden-import "sqlite3" ^
  --hidden-import "tkinter" ^
  --hidden-import "tkinter.filedialog" ^
  --paths "." ^
  gui\main.py ^
  2>&1

echo.
if exist "dist\MusicTools\MusicTools.exe" (
  echo BUILD SUCCESS: dist\MusicTools\MusicTools.exe exists
) else (
  echo BUILD FAILED: exe not found in dist\MusicTools\
)

echo.
echo Build finished: %DATE% %TIME%
echo.
pause
