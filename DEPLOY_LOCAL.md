# Deploy Local AmigoPet

Use `deploy_amigopet.bat` no Windows para testar, commitar e enviar alteracoes para a branch `main`.

## Como Executar

No PowerShell ou Prompt de Comando, dentro da pasta do projeto:

```powershell
.\deploy_amigopet.bat
```

O script executa:

1. `git status`
2. `python -m pytest`
3. solicita a mensagem do commit
4. `git add .`
5. `git commit -m "mensagem informada"`
6. `git push origin main`

Depois do push, o Render deve iniciar o deploy automatico da branch `main`.

## Regras De Seguranca

- O script nao usa `git push --force`.
- O script nao apaga arquivos.
- Se `python -m pytest` falhar, o commit e o push sao cancelados.
- Se a mensagem do commit ficar vazia, o commit e o push sao cancelados.

## Antes De Usar

Confira se o GitHub remoto esta correto:

```powershell
git remote -v
```

Confira se voce esta na branch correta:

```powershell
git branch --show-current
```

O esperado para deploy automatico e:

```txt
origin -> https://github.com/robbertojustinno/amigopet_app.git
branch -> main
```
