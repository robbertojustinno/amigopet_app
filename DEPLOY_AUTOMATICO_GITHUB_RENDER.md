# Deploy Automatico GitHub + Render - AmigoPet

Este guia descreve o fluxo seguro para enviar alteracoes locais ao GitHub e acionar deploy automatico no Render pela branch `main`.

## Estado Validado Do Projeto

- Branch local atual: `main`.
- Remote GitHub configurado: `origin` -> `https://github.com/robbertojustinno/amigopet_app.git`.
- Backend servido por FastAPI em `backend.app.main:app`.
- Frontend servido pelo proprio backend a partir de `frontend/`.
- Migrations versionadas em `migrations/`.
- `render.yaml` esta configurado como Web Service Python.
- `render.yaml` executa `pip install -r requirements.txt` no build.
- `render.yaml` executa `alembic upgrade head` antes do Uvicorn.
- `Procfile` tambem executa `alembic upgrade head` antes do Uvicorn.
- `runtime.txt` fixa Python em `python-3.11.9`.
- `requirements.txt` inclui FastAPI, Uvicorn, SQLAlchemy, PostgreSQL, Redis, Alembic e dependencias de teste.
- `migrations/env.py` usa `DATABASE_URL` do ambiente e normaliza `postgres://` para `postgresql://`.

## Arquivos De Deploy

`render.yaml`:

```yaml
services:
  - type: web
    name: amigopet
    runtime: python
    buildCommand: pip install -r requirements.txt
    startCommand: alembic upgrade head && python -m uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT
```

`Procfile`:

```txt
web: alembic upgrade head && uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT
```

O `render.yaml` deve ser a referencia principal no Render. O `Procfile` fica como fallback compativel.

## Variaveis Obrigatorias No Render

Configure no painel do Render, em `Environment`:

```env
APP_ENV=production
SESSION_SECRET=uma_chave_aleatoria_com_32_ou_mais_caracteres
CORS_ORIGINS=https://SEU-SERVICO.onrender.com
DATABASE_URL=postgresql://usuario:senha@host:5432/banco
PUBLIC_BASE_URL=https://SEU-SERVICO.onrender.com
```

Se usar Google Login:

```env
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=https://SEU-SERVICO.onrender.com/api/auth/google/callback
```

Se usar Asaas:

```env
ASAAS_API_KEY=...
ASAAS_WEBHOOK_TOKEN=...
ASAAS_ENV=production
ASAAS_BASE_URL=https://api.asaas.com/v3
```

Se usar Redis:

```env
REDIS_URL=redis://usuario:senha@host:6379/0
```

Observacao: o app ja faz fallback de rate limit para memoria quando Redis nao estiver disponivel. Redis continua recomendado para WebSocket/eventos em ambiente com multiplas instancias.

## Configurar Deploy Automatico No Render

1. Acesse o painel do Render.
2. Abra o Web Service `amigopet`.
3. Confirme que o servico esta conectado ao repositorio:

```txt
https://github.com/robbertojustinno/amigopet_app
```

4. Confirme a branch:

```txt
main
```

5. Confirme que `Auto-Deploy` esta habilitado.
6. Confirme que o ambiente usa o arquivo `render.yaml` ou os comandos equivalentes:

```txt
Build Command: pip install -r requirements.txt
Start Command: alembic upgrade head && python -m uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT
```

7. Confirme que existe um banco PostgreSQL associado e que `DATABASE_URL` esta definido.
8. Salve as alteracoes.

Depois disso, todo `git push origin main` deve iniciar um deploy automatico.

## Fluxo Seguro Para Enviar Alteracoes

Antes de commitar:

```powershell
git status --short
python -m pytest
python -m alembic heads
```

Revise os arquivos alterados:

```powershell
git diff --stat
git diff
```

Adicione apenas os arquivos desejados:

```powershell
git add caminho/do/arquivo
```

Confira o que vai entrar no commit:

```powershell
git status --short
git diff --cached --stat
git diff --cached
```

Crie o commit:

```powershell
git commit -m "Descreva a alteracao"
```

Envie para o GitHub:

```powershell
git push origin main
```

## Validar Deploy No Render

1. Acesse o Web Service no Render.
2. Abra a aba `Events` ou `Logs`.
3. Confirme que o deploy iniciou apos o push.
4. Confirme no log:

```txt
alembic upgrade head
uvicorn backend.app.main:app
```

5. Confirme que o servico ficou `Live`.
6. Acesse:

```txt
https://SEU-SERVICO.onrender.com/
https://SEU-SERVICO.onrender.com/passeador
https://SEU-SERVICO.onrender.com/admin
```

## Rollback Seguro

Para voltar ao commit anterior sem reescrever historico:

```powershell
git log --oneline -5
git revert HASH_DO_COMMIT
git push origin main
```

O Render fara novo deploy automatico com o revert.

## Checklist Final

- `git status --short` mostra apenas alteracoes intencionais antes do commit.
- `python -m pytest` passa localmente.
- `render.yaml` usa `alembic upgrade head` antes do Uvicorn.
- `DATABASE_URL` esta configurado no Render.
- `SESSION_SECRET` tem 32 ou mais caracteres.
- `CORS_ORIGINS` aponta para o dominio real do Render ou dominio proprio.
- Render esta conectado ao GitHub na branch `main`.
- Auto-Deploy esta habilitado no Render.
- Push em `main` inicia deploy automatico.
