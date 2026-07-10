# Checklist Render Producao - AmigoPet

Data da checagem: 2026-07-10

## Resultado Geral

Status: quase pronto para Render, com pontos obrigatorios a conferir no painel antes do deploy.

Validacoes locais executadas:

```powershell
python -m alembic heads
python -m alembic current
python -m pytest
```

Resultado:

- Alembic head encontrado: `20260709_0001`.
- Alembic carregou a configuracao local sem erro.
- Testes: `18 passed`.

## Configuracao Render Encontrada

Arquivo principal: `render.yaml`

```yaml
services:
  - type: web
    name: amigopet
    runtime: python
    buildCommand: pip install -r requirements.txt
    startCommand: alembic upgrade head && python -m uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT
```

Status:

- Build command: correto para o layout atual, pois usa o `requirements.txt` da raiz.
- Start command: correto, pois roda `alembic upgrade head` antes do Uvicorn.
- Porta: correta, usa `$PORT` do Render.
- App import path: correto, `backend.app.main:app`.

Arquivo secundario: `Procfile`

```txt
web: alembic upgrade head && uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT
```

Status:

- Coerente com o `render.yaml`.
- Deve ser tratado como fallback. O `render.yaml` deve ser a fonte principal.

## Variaveis Obrigatorias

Configure no Render em `Environment`.

### Ambiente

Obrigatorio:

```env
APP_ENV=production
```

Observacao:

- O backend tambem aceita `ENV=production`, mas padronize `APP_ENV=production`.
- Se `RENDER_EXTERNAL_URL` estiver definido pelo Render, o backend tambem considera ambiente de producao.

### SESSION_SECRET

Obrigatorio em producao:

```env
SESSION_SECRET=valor_aleatorio_com_32_ou_mais_caracteres
```

Regra no backend:

- Em producao, se `SESSION_SECRET` tiver menos de 32 caracteres, a aplicacao falha ao iniciar.

Risco:

- `.env.example` ainda usa `SECRET_KEY`, mas o backend atual exige `SESSION_SECRET`.
- No Render, use `SESSION_SECRET`, nao `SECRET_KEY`.

### CORS_ORIGINS

Obrigatorio em producao:

```env
CORS_ORIGINS=https://SEU-SERVICO.onrender.com
```

Se houver dominio proprio:

```env
CORS_ORIGINS=https://SEU-SERVICO.onrender.com,https://seudominio.com
```

Regras no backend:

- Em producao, `CORS_ORIGINS` nao pode ficar vazio.
- Em producao, `CORS_ORIGINS` nao pode usar wildcard `*`.

### DATABASE_URL

Obrigatorio para producao real:

```env
DATABASE_URL=postgresql://usuario:senha@host:5432/banco
```

Status:

- `backend/app/main.py` le `DATABASE_URL`.
- `migrations/env.py` tambem le `DATABASE_URL`.
- `postgres://` e normalizado para `postgresql://`.
- Se `DATABASE_URL` nao existir, o app cai para SQLite local `sqlite:///./amigopet_v6.db`, o que nao e adequado para producao Render.

Risco:

- Sem PostgreSQL persistente, dados podem ser perdidos entre deploys/restarts.

### PUBLIC_BASE_URL

Obrigatorio para URLs publicas e callbacks:

```env
PUBLIC_BASE_URL=https://SEU-SERVICO.onrender.com
```

Status:

- Se `PUBLIC_BASE_URL` nao existir, o backend tenta usar `RENDER_EXTERNAL_URL`.
- Recomendado configurar explicitamente para evitar callbacks incorretos.

### Google OAuth

Obrigatorio se login Google estiver ativo:

```env
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=https://SEU-SERVICO.onrender.com/api/auth/google/callback
```

Status:

- `GOOGLE_REDIRECT_URI` e derivado de `PUBLIC_BASE_URL` se nao for informado.
- Para evitar divergencia com o Google Cloud, configure explicitamente.

Riscos:

- Redirect URI no Google Cloud deve ser exatamente igual ao valor no Render.
- Para APK Android com navegador externo, o dominio deve bater com o dominio publico do Render.

### Asaas

Obrigatorio se PIX/repasse real estiver ativo:

```env
ASAAS_API_KEY=...
ASAAS_WEBHOOK_TOKEN=...
ASAAS_ENV=production
ASAAS_BASE_URL=https://api.asaas.com/v3
```

Status:

- `ASAAS_API_KEY` e exigida quando o app cria cobrancas, consulta pagamentos ou faz repasses.
- `ASAAS_WEBHOOK_TOKEN` e exigido para validar webhook em producao.
- `ASAAS_BASE_URL` tem default de producao.

Riscos:

- Sem `ASAAS_API_KEY`, fluxos de PIX real falham.
- Sem `ASAAS_WEBHOOK_TOKEN`, webhooks em producao nao devem ser aceitos.

### Redis

Opcional:

```env
REDIS_URL=redis://usuario:senha@host:6379/0
```

Status:

- Rate limit tem fallback em memoria se Redis estiver ausente ou indisponivel.
- WebSocket/eventos usam Redis quando `REDIS_URL` existe.

Risco:

- Sem Redis, eventos em tempo real ficam limitados a memoria da instancia atual.
- Para mais de uma instancia no Render, Redis e recomendado.

## Alembic

Arquivos:

- `alembic.ini`
- `migrations/env.py`
- `migrations/versions/20260709_0001_initial_schema.py`

Status:

- `script_location = migrations`.
- `migrations/env.py` injeta `DATABASE_URL` no Alembic.
- Existe uma revision head: `20260709_0001`.
- `render.yaml` executa `alembic upgrade head` antes de iniciar o backend.

Validacao executada:

```txt
20260709_0001 (head)
```

Riscos:

- Se `DATABASE_URL` apontar para banco errado, Alembic migrara o banco errado.
- Se a migration falhar, o servico nao sobe, porque ela roda no start command.

## Requirements

Arquivo usado pelo Render atual:

```txt
requirements.txt
```

Status:

- Inclui `fastapi`, `uvicorn`, `sqlalchemy`, `psycopg2-binary`, `redis`, `alembic`, `pytest`, `httpx`.

Duplicidade:

- Existe tambem `backend/requirements.txt`.
- `backend/requirements.txt` inclui `uvicorn[standard]`, `websockets` e `wsproto`.
- `requirements.txt` da raiz usa apenas `uvicorn`.

Risco:

- Como `render.yaml` instala o `requirements.txt` da raiz, dependencias extras de WebSocket presentes apenas em `backend/requirements.txt` podem nao ser instaladas no Render.
- Se WebSocket falhar em producao, alinhar os dois requirements ou usar `uvicorn[standard]` no arquivo da raiz.

## Runtime

Arquivos:

- `runtime.txt`
- `backend/runtime.txt`

Status:

- Ambos usam `python-3.11.9`.
- Coerente para Render Python runtime.

## Arquivos Duplicados Ou Potencialmente Confusos

Duplicidades relevantes:

- `requirements.txt` e `backend/requirements.txt`.
- `runtime.txt` e `backend/runtime.txt`.
- `Procfile` e `render.yaml`.
- `app.js` na raiz e `frontend/app.js`.
- `index.html` na raiz e `frontend/index.html`.
- `styles.css` na raiz e `frontend/styles.css`.
- `backend/app/main.py`, `backend/app/main_backup_google.py` e `backend_patch/app/main.py`.
- Zips de patches e backups na raiz.
- Build Android gerado em `cliente/build/` e `passeador/build/`.

Impacto:

- O deploy Python via `render.yaml` usa a raiz do repositorio.
- O backend serve arquivos de `frontend/`, nao os HTML/CSS/JS duplicados da raiz.
- Backups e patches nao devem ser usados pelo Render, mas aumentam risco de confusao e tamanho do repositorio.

Recomendacao operacional:

- Antes de deploy, revisar `git status --short`.
- Nao commitar bancos SQLite locais, builds Android, zips temporarios ou pastas de build.

## Riscos De Deploy

1. Variaveis de producao ausentes

- Sem `SESSION_SECRET` valido, app nao inicia.
- Sem `CORS_ORIGINS`, app nao inicia em producao.
- Sem `DATABASE_URL`, app usa SQLite local, inadequado para Render.

2. `.env.example` desatualizado

- Mostra `SECRET_KEY`, mas o backend exige `SESSION_SECRET`.
- Mostra SQLite antigo `amigopet.db`, mas o backend usa fallback `amigopet_v6.db`.

3. Requirements duplicados

- Render usa `requirements.txt` da raiz.
- `backend/requirements.txt` tem dependencias extras de WebSocket.

4. Artefatos e backups no repositorio

- Zips, backups e builds podem aumentar tempo de build e confundir manutencao.

5. Alembic no start command

- E correto para garantir schema atualizado.
- Mas se migration falhar, o app nao sobe. Verificar logs do Render imediatamente apos deploy.

6. Redis opcional

- Rate limit nao deve bloquear login por falta de Redis.
- WebSocket multi-instancia fica limitado sem Redis.

## Checklist Antes Do Deploy

- [ ] `APP_ENV=production` configurado.
- [ ] `SESSION_SECRET` configurado com 32+ caracteres.
- [ ] `CORS_ORIGINS` configurado sem wildcard.
- [ ] `DATABASE_URL` apontando para PostgreSQL persistente.
- [ ] `PUBLIC_BASE_URL` apontando para o dominio publico final.
- [ ] `ASAAS_API_KEY` configurada se PIX real estiver ativo.
- [ ] `ASAAS_WEBHOOK_TOKEN` configurado se webhook Asaas estiver ativo.
- [ ] `GOOGLE_CLIENT_ID` configurado se login Google estiver ativo.
- [ ] `GOOGLE_CLIENT_SECRET` configurado se login Google estiver ativo.
- [ ] `GOOGLE_REDIRECT_URI` registrado no Google Cloud e igual ao Render.
- [ ] `REDIS_URL` configurado se precisar WebSocket/eventos multi-instancia.
- [ ] Render conectado ao GitHub na branch `main`.
- [ ] Auto deploy habilitado no Render.
- [ ] Build command igual a `pip install -r requirements.txt`.
- [ ] Start command igual a `alembic upgrade head && python -m uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT`.
- [ ] `python -m pytest` passando localmente.
- [ ] `python -m alembic heads` retornando `20260709_0001 (head)`.
- [ ] `git status --short` revisado antes do push.

## Comandos De Validacao Local

```powershell
git status --short
python -m pytest
python -m alembic heads
python -m alembic current
```

## Conclusao

O projeto esta estruturalmente preparado para deploy no Render via `render.yaml`, desde que as variaveis de producao sejam configuradas corretamente no painel do Render.

Os principais pontos de atencao antes do deploy sao:

- configurar `SESSION_SECRET`, `CORS_ORIGINS`, `DATABASE_URL` e `PUBLIC_BASE_URL`;
- configurar Asaas e Google se esses fluxos estiverem ativos;
- revisar duplicidade de `requirements.txt` se WebSocket apresentar problema no Render;
- evitar commitar artefatos locais, bancos SQLite, zips e builds gerados.
