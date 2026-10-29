@echo off
REM ---------------------------------------------------------------------
REM Builds dist\ManualImageCropping.exe from manual_cropping.py
REM Developed by the GAAA research group
REM Software created by Dennis da Silva Ferreira
REM ---------------------------------------------------------------------
cd /d "%~dp0"

echo [1/3] Installing/updating PyInstaller...
".venv\Scripts\python.exe" -m pip install --upgrade pyinstaller || goto :error

echo [2/3] Generating the icon from the GAAA logo...
".venv\Scripts\python.exe" assets\generate_icon.py || goto :error

echo [3/3] Building the executable...
".venv\Scripts\pyinstaller.exe" ManualImageCropping.spec --noconfirm --clean || goto :error

echo.
echo Done: dist\ManualImageCropping.exe
pause
exit /b 0

:error
echo.
echo FAILED. Check the messages above.
pause
exit /b 1
