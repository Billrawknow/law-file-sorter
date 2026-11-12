@echo off
REM Builds "Document Sorter.exe" - a single file staff can run without Python.
REM Run this on Windows from the project folder (double-click it, or run build_exe.bat in a terminal).

python -m pip install --upgrade pyinstaller
python -m PyInstaller --noconfirm --onefile --windowed ^
  --name "Document Sorter" ^
  --icon icon.ico ^
  --add-data "icon.ico;." ^
  sorter_app.py

echo.
echo Done. Your app is in the "dist" folder: dist\Document Sorter.exe
pause
