@echo off
REM ---------------------------------------------------------------------
REM Gera o dist\RecorteManual.exe a partir de recorte_manual.py
REM Desenvolvido pelo grupo de pesquisa GAAA
REM Software criado por Dennis da Silva Ferreira
REM ---------------------------------------------------------------------
cd /d "%~dp0"

echo [1/3] Instalando/atualizando o PyInstaller...
".venv\Scripts\python.exe" -m pip install --upgrade pyinstaller || goto :erro

echo [2/3] Gerando o icone a partir da logomarca do GAAA...
".venv\Scripts\python.exe" assets\gerar_icone.py || goto :erro

echo [3/3] Compilando o executavel...
".venv\Scripts\pyinstaller.exe" RecorteManual.spec --noconfirm --clean || goto :erro

echo.
echo Pronto: dist\RecorteManual.exe
pause
exit /b 0

:erro
echo.
echo FALHOU. Confira as mensagens acima.
pause
exit /b 1
