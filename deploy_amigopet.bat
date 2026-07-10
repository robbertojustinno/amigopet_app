@echo off
setlocal enabledelayedexpansion

echo.
echo === AmigoPet Deploy Local GitHub + Render ===
echo.

git status
if errorlevel 1 (
    echo.
    echo ERRO: Nao foi possivel executar git status.
    exit /b 1
)

echo.
echo Executando testes...
python -m pytest
if errorlevel 1 (
    echo.
    echo ERRO: pytest falhou. Commit e push foram cancelados.
    exit /b 1
)

echo.
set "COMMIT_MSG="
set /p COMMIT_MSG=Informe a mensagem do commit: 

if "%COMMIT_MSG%"=="" (
    echo.
    echo ERRO: mensagem do commit vazia. Commit e push foram cancelados.
    exit /b 1
)

echo.
echo Adicionando arquivos ao Git...
git add .
if errorlevel 1 (
    echo.
    echo ERRO: git add falhou.
    exit /b 1
)

echo.
echo Criando commit...
git commit -m "%COMMIT_MSG%"
if errorlevel 1 (
    echo.
    echo ERRO: git commit falhou. Verifique se existem alteracoes para commitar.
    exit /b 1
)

echo.
echo Enviando para origin main...
git push origin main
if errorlevel 1 (
    echo.
    echo ERRO: git push origin main falhou.
    exit /b 1
)

echo.
echo Deploy enviado com sucesso.
echo O Render iniciara o deploy automatico apos receber o push na branch main.
echo Acompanhe o progresso no painel do Render.

exit /b 0
