@echo off
REM Instala as dependencias do Python (rode uma vez)
cd /d "%~dp0"
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo ERRO na instalacao. Copie a mensagem acima e envie para o suporte.
) else (
  echo.
  echo Dependencias instaladas com sucesso.
)
pause
