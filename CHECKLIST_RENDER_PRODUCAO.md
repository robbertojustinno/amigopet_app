# Checklist Render Producao - AmigoPet

Data da checagem: 2026-07-10

## Resultado Geral

Status: pronto estruturalmente para deploy no Render, desde que as variaveis obrigatorias estejam configuradas corretamente no painel do Render.

Validacoes executadas localmente:

```powershell
python -m alembic heads
python -m alembic current
python -m pytest
```

Resultado:

- Alembic head: `20260709_0001 (head)`.
- Alembic carregou a configuracao local sem erro.
- Testes: `19 passed`.
- `git status --short`: limpo antes da geracao deste checklist.

## Build Command

Arquivo principal: `render.yaml`

```yaml
buildCommand: pip install -r requirements.txt
```

Status:

- Correto para o deploy Python nativo pela raiz do repositorio.
- Instala o `requirements.txt` da raiz, nao `backend/requirements.txt`.

Risco:

- Existe `backend/requirements.txt` com dependencias extras (`uvicorn[standard]`, `websockets`, `wsproto`).
- Se o WebSocket apresentar problema no Render, alinhar o `requirements.txt` da raiz com o `backend/requirements.txt`.

## Start Command

Arquivo principal: `render.yaml`

```yaml
startCommand: alembic upgrade head && python -m uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT
```

Status:

- Correto.
- Executa migrations antes de subir o app.
- Usa `$PORT`, exigido pelo Render.
- Importa corretamente `backend.app.main:app`.

Arquivo secundario: `Procfile`

```txt
web: alembic upgrade head && uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT
```

Status:

- Coerente com `render.yaml`.
- Deve ser tratado como fallback. O Render deve usar `render.yaml` como fonte principal.

## Runtime

Arquivos encontrados:

- `runtime.txt`
- `backend/runtime.txt`

Conteudo:

```txt
python-3.11.9
```

Status:

- Correto e consistente entre raiz e `backend/`.

## Variaveis Obrigatorias No Render

Configure no painel do Render em `Environment`.

### APP_ENV

Obrigatorio:

```env
APP_ENV=production
```

Observacoes:

- O backend tambem aceita `ENV=production`.
- Padrao recomendado: `APP_ENV=production`.
- Se `RENDER_EXTERNAL_URL` existir, o backend tambem considera ambiente de producao.

### SESSION_SECRET

Obrigatorio:

```env
SESSION_SECRET=valor_aleatorio_com_32_ou_mais_caracteres
```

Regra validada no backend:

- Em producao, a aplicacao falha ao iniciar se `SESSION_SECRET` tiver menos de 32 caracteres.

Risco:

- `.env.example` ainda mostra `SECRET_KEY`, mas o backend atual exige `SESSION_SECRET`.
- No Render, configurar `SESSION_SECRET`; `SECRET_KEY` nao atende essa validacao.

### CORS_ORIGINS

Obrigatorio:

```env
CORS_ORIGINS=https://SEU-SERVICO.onrender.com
```

Com dominio proprio:

```env
CORS_ORIGINS=https://SEU-SERVICO.onrender.com,https://seudominio.com
```

Regras validada no backend:

- Em producao, nao pode ficar vazio.
- Em producao, nao pode usar wildcard `*`.

### DATABASE_URL

Obrigatorio para producao real:

```env
DATABASE_URL=postgresql://usuario:senha@host:5432/banco
```

Status:

- `backend/app/main.py` usa `DATABASE_URL`.
- `migrations/env.py` usa `DATABASE_URL`.
- URLs `postgres://` sao normalizadas para `postgresql://`.

Risco:

- Se `DATABASE_URL` nao existir, o app cai para SQLite local `sqlite:///./amigopet_v6.db`.
- SQLite local no Render nao e adequado para producao porque dados podem ser perdidos em restart/deploy.

### PUBLIC_BASE_URL

Obrigatorio recomendado:

```env
PUBLIC_BASE_URL=https://SEU-SERVICO.onrender.com
```

Status:

- Se ausente, o backend tenta usar `RENDER_EXTERNAL_URL`.
- Recomendado configurar explicitamente para callbacks e webhooks.

### ASAAS_API_KEY

Obrigatorio se PIX/Asaas estiver ativo:

```env
ASAAS_API_KEY=...
```

Status:

- Exigido para criar cobranca PIX, consultar pagamento e fazer repasse.

Risco:

- Sem `ASAAS_API_KEY`, o convite pode ser criado, mas a geracao/consulta PIX real falhara.

### ASAAS_WEBHOOK_TOKEN

Obrigatorio para webhook Asaas em producao:

```env
ASAAS_WEBHOOK_TOKEN=...
```

Status:

- Usado para validar o header recebido do Asaas.

Risco:

- Sem token correto, webhooks validos podem ser recusados ou ambiente pode ficar inseguro se configurado incorretamente.

### ASAAS_ENV e ASAAS_BASE_URL

Recomendado em producao:

```env
ASAAS_ENV=production
ASAAS_BASE_URL=https://api.asaas.com/v3
```

Status:

- `ASAAS_BASE_URL` tem default de producao.
- Em sandbox/test, o backend troca para `https://api-sandbox.asaas.com/v3` quando aplicavel.

### GOOGLE_CLIENT_ID

Obrigatorio se login Google estiver ativo:

```env
GOOGLE_CLIENT_ID=...
```

Status:

- Necessario para iniciar OAuth.

### GOOGLE_CLIENT_SECRET

Obrigatorio se login Google estiver ativo:

```env
GOOGLE_CLIENT_SECRET=...
```

Status:

- Necessario para trocar `code` por token no callback.

### GOOGLE_REDIRECT_URI

Obrigatorio recomendado:

```env
GOOGLE_REDIRECT_URI=https://SEU-SERVICO.onrender.com/api/auth/google/callback
```

Status:

- Se ausente, e derivado de `PUBLIC_BASE_URL`.

Risco:

- Deve bater exatamente com o redirect cadastrado no Google Cloud.
- Divergencia causa falha no login Google.

### REDIS_URL

Opcional:

```env
REDIS_URL=redis://usuario:senha@host:6379/0
```

Status:

- Rate limit usa Redis se disponivel.
- Se Redis nao existir ou falhar, rate limit cai para memoria.
- WebSocket/eventos usam Redis quando disponivel.

Risco:

- Sem Redis, eventos em tempo real ficam limitados a memoria da instancia.
- Para multiplas instancias no Render, Redis e recomendado.

## Alembic

Arquivos:

- `alembic.ini`
- `migrations/env.py`
- `migrations/versions/20260709_0001_initial_schema.py`

Status:

- `script_location = migrations`.
- `migrations/env.py` injeta `DATABASE_URL` no Alembic.
- Existe uma unica revision head: `20260709_0001`.
- `render.yaml` roda `alembic upgrade head` antes do app iniciar.

Validacao local:

```txt
20260709_0001 (head)
```

Riscos:

- Migration falhando impede o app de iniciar, pois roda no start command.
- `DATABASE_URL` incorreto migrara o banco errado.

## Arquivos Duplicados Ou Potencialmente Confusos

Duplicidades relevantes encontradas:

- `requirements.txt` e `backend/requirements.txt`.
- `runtime.txt` e `backend/runtime.txt`.
- `render.yaml` e `Procfile`.
- `backend/Dockerfile` e `render.yaml` Python nativo.
- `backend/start.sh` e start command do Render.
- `app.js` na raiz e `frontend/app.js`.
- `index.html` na raiz e `frontend/index.html`.
- `styles.css` na raiz e `frontend/styles.css`.
- `backend/app/main.py`, `backend/app/main_backup_google.py` e `backend_patch/app/main.py`.
- Arquivos `.zip` de patches/backups na raiz.
- Pastas de patch locais: `amigopet_fix_payout_error_patch`, `amigopet_wallet_clean_patch`.

Impacto:

- O deploy atual pelo `render.yaml` usa a raiz do repositorio.
- O backend serve o frontend de `frontend/`.
- Arquivos web duplicados na raiz nao sao a fonte servida pelo backend.
- Backups, zips e patches podem aumentar tempo de build e causar confusao operacional.

## Riscos De Deploy

1. Variaveis obrigatorias ausentes

- `SESSION_SECRET` ausente/curto: app nao inicia.
- `CORS_ORIGINS` ausente em producao: app nao inicia.
- `DATABASE_URL` ausente: app usa SQLite local, inadequado para producao.

2. `.env.example` desatualizado

- Mostra `SECRET_KEY`, mas o backend exige `SESSION_SECRET`.
- Mostra `sqlite:///./amigopet.db`, enquanto o fallback atual e `sqlite:///./amigopet_v6.db`.

3. Requirements duplicados

- Render instala `requirements.txt` da raiz.
- Dependencias extras de WebSocket existem apenas em `backend/requirements.txt`.

4. Artefatos no repositorio

- Zips, backups, builds Android e arquivos duplicados podem aumentar tempo de build.
- Antes de push/deploy, revisar `git status --short`.

5. Alembic no start command

- Correto para garantir schema atualizado.
- Se migration falhar, deploy fica indisponivel ate corrigir banco/migration.

6. Redis opcional

- Rate limit nao deve bloquear login por ausencia de Redis.
- WebSocket multi-instancia exige Redis para consistencia entre instancias.

7. Asaas

- Sem `ASAAS_API_KEY`, convites podem ser criados, mas PIX real falha.
- Sem `ASAAS_WEBHOOK_TOKEN`, confirmacao automatica por webhook falha em producao.

8. Google OAuth

- `GOOGLE_REDIRECT_URI` precisa ser identico no Render e Google Cloud.
- Para APK Android com navegador externo, o host publico precisa ser o mesmo dominio configurado.

## Checklist Antes Do Deploy

- [ ] `APP_ENV=production`
- [ ] `SESSION_SECRET` com 32+ caracteres
- [ ] `CORS_ORIGINS` sem wildcard e apontando para dominio real
- [ ] `DATABASE_URL` PostgreSQL persistente
- [ ] `PUBLIC_BASE_URL` com URL publica final
- [ ] `ASAAS_API_KEY` configurada se PIX real estiver ativo
- [ ] `ASAAS_WEBHOOK_TOKEN` configurado se webhook Asaas estiver ativo
- [ ] `ASAAS_ENV=production`
- [ ] `GOOGLE_CLIENT_ID` configurado se login Google estiver ativo
- [ ] `GOOGLE_CLIENT_SECRET` configurado se login Google estiver ativo
- [ ] `GOOGLE_REDIRECT_URI` registrado no Google Cloud
- [ ] `REDIS_URL` configurado se precisar WebSocket/eventos multi-instancia
- [ ] Render conectado ao GitHub na branch `main`
- [ ] Auto deploy habilitado no Render
- [ ] Build command: `pip install -r requirements.txt`
- [ ] Start command: `alembic upgrade head && python -m uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT`
- [ ] `python -m pytest` passando localmente
- [ ] `python -m alembic heads` retornando `20260709_0001 (head)`
- [ ] `git status --short` revisado antes do push

## Comandos De Validacao Local

```powershell
git status --short
python -m pytest
python -m alembic heads
python -m alembic current
```

## Conclusao

O projeto esta pronto para deploy no Render pelo `render.yaml` da raiz, desde que as variaveis de producao sejam configuradas no painel do Render.

Prioridades antes do deploy:

1. Configurar `SESSION_SECRET`, `CORS_ORIGINS`, `DATABASE_URL` e `PUBLIC_BASE_URL`.
2. Configurar Asaas e Google se os fluxos estiverem ativos.
3. Confirmar Auto Deploy na branch `main`.
4. Revisar duplicidades/artefatos antes de commitar para evitar enviar arquivos desnecessarios.
