@echo off
echo Installing PyInstaller...
pip install pyinstaller

echo.
echo Building executable...
pyinstaller mtg_stories.spec

echo.
echo Done! Executable is at: dist\MTG to EPUB.exe
pause
