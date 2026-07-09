# AUDITORIA FINAL AMIGOPET

Data: 2026-07-09  
Escopo: auditoria final após correções V3-H01, V3-H02 e V3-H03.  
Modo: revisão estática, execução de testes automatizados e verificação de deploy/configuração, sem alteração de código. Única escrita realizada: este relatório.

## 1. Resultado executivo

O AmigoPet está em estado substancialmente mais seguro do que na auditoria V3. Os três bloqueadores altos identificados foram tratados:

- `V3-H01`: APKs Android não mantêm mais URL fixa no código Java; URL é definida via `BuildConfig`/propriedade de build.
- `V3-H02`: finalização de passeio ficou idempotente para impedir novo repasse quando `payout_transfer_id` já existe e evita duplicar eventos/mensagens em chamadas repetidas.
- `V3-H03`: rate limiting usa Redis quando configurado e falha fechado em produção quando Redis não está disponível, mantendo fallback em memória apenas fora de produção.

Os testes automatizados passaram:

```text
python -m pytest
16 passed, 164 warnings in 9.05s
```

Classificação final: **apto para staging/preprodução com checklist obrigatório de ambiente**, mas ainda recomendo não liberar produção com pagamento real antes de:

1. Configurar e validar Redis real em produção.
2. Executar Alembic contra cópia sanitizada do banco PostgreSQL real.
3. Compilar os APKs em ambiente Android com `JAVA_HOME`/SDK configurados.
4. Atualizar `.env.example`/runbook de deploy.

## 2. Verificações executadas

### Testes automatizados

Resultado:

```text
16 passed, 164 warnings
```

Warnings observados:

- `FastAPI @app.on_event("startup")` depreciado.
- `datetime.utcnow()` depreciado no Python 3.12.

Esses warnings não quebram a suíte, mas devem entrar em backlog técnico.

### Build Android

Comando tentado:

```text
.\gradlew.bat :cliente:assembleDebug :passeador:assembleDebug
```

Resultado:

```text
ERROR: JAVA_HOME is not set and no 'java' command could be found in your PATH.
```

Conclusão: não foi possível compilar Android neste ambiente. A auditoria Android foi estática.

### Estado de trabalho

No início da auditoria final, `git status --short` retornou limpo.

## 3. Status das correções V3-H01, V3-H02 e V3-H03

| Item | Status final | Evidência |
|---|---:|---|
| V3-H01 - URL fixa Render nos APKs | Corrigido no código Java | `MainActivity.java` de cliente e passeador usam `BuildConfig.APP_URL`; endpoints Google do passeador usam `BuildConfig.API_BASE_URL`. |
| V3-H02 - Repasse duplicado na finalização | Corrigido | `finish_walk` retorna imediatamente se `status == "finalizado"` e não cria novo repasse se `payout_transfer_id` já existe. Há teste de dupla finalização. |
| V3-H03 - Rate limit em memória | Corrigido para produção | `enforce_rate_limit` usa Redis via `REDIS_URL`; em produção sem Redis funcional retorna `503`, sem fallback em memória. Há testes com Redis fake e fallback local. |

## 4. Segurança backend

### Pontos validados

- Produção exige `SESSION_SECRET` forte.
- Produção exige `CORS_ORIGINS` explícito e sem wildcard.
- Cookies de sessão são assinados via HMAC.
- CSRF aplicado em mutações autenticadas por cookie.
- Hash de senha com bcrypt e compatibilidade com legado.
- Cadastro público não cria admin.
- Endpoints administrativos exigem usuário admin real.
- Operações de passeio exigem papel correto e participação/propriedade.
- DTOs por contexto reduzem exposição de dados.
- WebSocket exige sessão válida.
- Rate limiting cobre autenticação, reset, criação de pedidos, webhooks e endpoints sensíveis.

### Riscos remanescentes

| Risco | Severidade | Observação |
|---|---:|---|
| Sessão stateless sem revogação server-side | Média | Logout remove cookie local; cookie roubado continua válido até expiração/rotação de segredo. |
| CSP ainda usa `unsafe-inline` | Média | Necessário para preservar frontend atual, mas reduz proteção contra XSS. |
| `@app.on_event` e `datetime.utcnow()` depreciados | Baixa | Não bloqueia produção, mas gera dívida técnica. |
| Backend ainda monolítico | Média | `backend/app/main.py` concentra rotas, modelos, serviços, WebSocket, pagamentos e configuração. |
| Seeds/configurações ainda executam no import | Média/Baixa | Credenciais padrão foram removidas de produção, mas configurações administrativas continuam inicializadas implicitamente. |

## 5. Rate limit Redis

Status: corrigido para produção.

Comportamento observado no código:

- Chave inclui escopo, IP e identificador.
- Usa pipeline transacional Redis com `INCR` + `EXPIRE`.
- Retorna `429` com `Retry-After` quando excede limite.
- Se `REDIS_URL` está configurado e Redis falha:
  - em produção: falha fechado com `503`;
  - fora de produção: cai para memória.
- Se `REDIS_URL` não está configurado:
  - em produção: falha fechado com `503`;
  - fora de produção: usa memória.

Recomendação operacional:

- Em produção, configurar `REDIS_URL` obrigatoriamente.
- Monitorar respostas `503` de rate limit, pois indicam falha de Redis.
- Usar Redis gerenciado com persistência/HA quando houver mais de uma instância.

## 6. Pagamentos e Asaas

### Pontos validados

- Webhook exige token em produção.
- Webhook consulta Asaas antes de confirmar pagamento.
- Valida:
  - payment id;
  - `externalReference`;
  - valor;
  - moeda;
  - customer quando disponível;
  - status conhecido.
- Processamento de confirmação de pagamento é idempotente.
- Finalização de passeio não cria novo repasse se `payout_transfer_id` já existe.
- Chamada repetida de finalização em passeio já finalizado retorna o estado atual sem gerar novos eventos/mensagens.

### Riscos remanescentes

| Risco | Severidade | Observação |
|---|---:|---|
| Webhook usa token compartilhado | Média | Se Asaas suportar assinatura HMAC/timestamp/IP allowlist, vale implementar como hardening adicional. |
| Transferência depende de disponibilidade Asaas no momento da finalização | Média | Falhas ficam registradas como erro/pendência; precisa processo operacional de retentativa controlada por admin. |
| Testes não cobrem concorrência real | Média | Duas finalizações simultâneas no mesmo instante devem ser testadas com banco transacional/PostgreSQL. |

## 7. WebSocket

Status: adequado para o estágio atual.

Pontos validados:

- `/ws` lê cookie de sessão.
- Fecha com `1008` quando usuário não existe/inativo.
- Eventos de digitação verificam participação no passeio.
- Eventos de passeio são enviados apenas a usuários autorizados.
- Redis pub/sub existe para múltiplas instâncias quando `REDIS_URL` está configurado.
- Sem Redis, WebSocket continua funcional em memória para instância única.

Riscos remanescentes:

- Não há teste com Redis real.
- Sem Redis, múltiplas instâncias não compartilham eventos.
- Não há heartbeat/controle robusto de conexão ociosa além do fluxo atual.

## 8. Android

Status: V3-H01 corrigido estaticamente; build não validada por falta de Java.

### Cliente

- `APP_URL` vem de `BuildConfig.APP_URL`.
- URL default de produção é definida no `cliente/build.gradle`.
- Pode ser sobrescrita no build:

```text
-PAMIGOPET_BASE_URL=https://seu-dominio.com
```

### Passeador

- `APP_URL` vem de `BuildConfig.APP_URL`.
- `API_BASE_URL` vem de `BuildConfig.API_BASE_URL`.
- Login Google nativo/web usa `API_BASE_URL`.
- URL default de produção permanece o host Render atual, preservando funcionamento existente.

### WebView

- Carrega internamente apenas:
  - host configurado da aplicação;
  - `accounts.google.com`;
  - `ssl.gstatic.com`;
  - `www.gstatic.com`.
- Demais links HTTP/HTTPS são enviados ao navegador externo.
- `usesCleartextTraffic="false"` está configurado.

Riscos remanescentes:

- `android:allowBackup="true"` continua ativo nos dois manifests; revisar antes de loja/produção.
- Build Android precisa ser executado em ambiente com Java/Android SDK.
- Host Render ainda existe como default de produção nos `build.gradle`; isso é configuração de build, não URL fixa no Java. Para domínio próprio, usar `-PAMIGOPET_BASE_URL`.

## 9. Frontend web e PWA

Pontos positivos:

- Frontend web deriva API/WS de `location.origin` ou `window.AMIGOPET_CONFIG`.
- SRI aplicado ao Leaflet externo.
- Uso de `innerHTML` está centralizado via `sanitizeHtml`/`setSafeHTML`.
- Admin valida sessão real via `/api/auth/session/current`.
- Service worker não cacheia `/api/` nem `/ws`.

Riscos remanescentes:

| Risco | Severidade | Observação |
|---|---:|---|
| CSP mantém `unsafe-inline` | Média | Necessário pelo frontend atual; remover em hardening futuro. |
| PWA pode servir shell antigo | Baixa/Média | Cache versionado existe, mas sem fluxo UX forte de atualização obrigatória. |
| `localStorage` usado como cache de usuário | Baixa | Sessão real é validada, mas dados locais devem seguir tratados como não confiáveis. |
| Arquivos frontend duplicados na raiz | Baixa | Backend ativo serve `frontend/`; duplicatas podem confundir manutenção/deploy estático externo. |

## 10. Deploy Render

Arquivos revisados:

- `render.yaml`
- `Procfile`
- `backend/Dockerfile`
- `backend/start.sh`
- `requirements.txt`
- `backend/requirements.txt`

Status:

- Deploy aponta para `backend.app.main`.
- Build instala dependências Python.
- Start executa `alembic upgrade head` antes de iniciar Uvicorn.
- Dependências incluem `redis`, `alembic`, `pytest`, `httpx`, `bcrypt`.

Riscos remanescentes:

| Risco | Severidade | Observação |
|---|---:|---|
| Migração roda no start do web process | Média | Em múltiplas instâncias, prefira etapa release/predeploy única. |
| `REDIS_URL` não está declarado em `render.yaml` | Média | Pode ser configurado no painel Render; precisa constar no runbook. |
| `CORS_ORIGINS` e `SESSION_SECRET` não aparecem no YAML | Média | Correto não commitar segredos, mas documentação/runbook precisa listar obrigatórios. |
| `.env.example` está desatualizado | Média | Ainda lista `SECRET_KEY`, `DATABASE_URL`, `APP_NAME`; falta a matriz real de variáveis. |

## 11. Alembic

Status: estrutura Alembic presente e usada no deploy.

Pontos positivos:

- `alembic.ini` existe.
- `migrations/env.py` lê `DATABASE_URL`.
- Migração inicial versionada existe.
- Startup do backend não depende mais de DDL improvisado no código da aplicação.

Riscos remanescentes:

- `target_metadata = None`; autogenerate não está configurado.
- Migração inicial contém normalização legada permissiva em PostgreSQL, incluindo ajustes de nulabilidade em `walk_requests`.
- Não foi executado teste contra PostgreSQL real nesta auditoria.

Recomendação antes de produção:

1. Criar banco staging PostgreSQL.
2. Restaurar dump sanitizado do banco real.
3. Rodar `alembic upgrade head`.
4. Validar constraints, índices e dados financeiros.
5. Só depois executar em produção.

## 12. Variáveis de ambiente

Obrigatórias/recomendadas para produção:

| Variável | Status esperado |
|---|---|
| `APP_ENV=production` ou `ENV=production` | Obrigatória |
| `SESSION_SECRET` | Obrigatória, forte, >= 32 chars |
| `CORS_ORIGINS` | Obrigatória, origens explícitas, sem wildcard |
| `DATABASE_URL` | Obrigatória, PostgreSQL em produção |
| `REDIS_URL` | Obrigatória se produção usa rate limit distribuído/múltiplas instâncias |
| `ASAAS_API_KEY` | Obrigatória para pagamentos reais |
| `ASAAS_WEBHOOK_TOKEN` | Obrigatória em produção |
| `PUBLIC_BASE_URL` | Recomendada/necessária para callbacks e URLs públicas |
| `GOOGLE_CLIENT_ID` | Necessária se login Google ativo |
| `GOOGLE_CLIENT_SECRET` | Necessária se login Google web/callback ativo |
| `GOOGLE_REDIRECT_URI` | Recomendada; fallback usa `PUBLIC_BASE_URL` |
| `SMTP_*` ou `RESEND_API_KEY`/`EMAIL_FROM` | Necessária para e-mails reais |
| `AMIGOPET_BASE_URL` | Propriedade de build Android, não env do backend |

Problema encontrado:

- `.env.example` está incompleto e usa `SECRET_KEY`, que não é o segredo de sessão atual (`SESSION_SECRET`).

## 13. Arquitetura

Pontos positivos:

- Fluxos críticos passaram a ter cobertura automatizada.
- Segurança de autenticação/autorização foi centralizada em dependências.
- Redis foi integrado para rate limit e WebSocket.
- Alembic substituiu DDL improvisado no startup.

Riscos estruturais:

- `backend/app/main.py` segue grande e concentrado.
- Módulos antigos em `backend/app/core`, `db`, `models`, `schemas`, `services` ainda podem confundir manutenção se não forem removidos/isolados.
- Falta pipeline CI completo com:
  - pytest;
  - build Android;
  - lint;
  - migração PostgreSQL staging;
  - testes E2E web.

## 14. Checklist final antes de produção

Bloqueios operacionais:

- [ ] Configurar `REDIS_URL` em produção e validar que rate limit não retorna `503`.
- [ ] Rodar `alembic upgrade head` em staging PostgreSQL com dump sanitizado.
- [ ] Compilar APK cliente e passeador com Java/Android SDK.
- [ ] Gerar APKs com `-PAMIGOPET_BASE_URL=https://dominio-oficial`.
- [ ] Atualizar `.env.example` e runbook de deploy.
- [ ] Configurar `SESSION_SECRET`, `CORS_ORIGINS`, `ASAAS_WEBHOOK_TOKEN`, `ASAAS_API_KEY`, Google OAuth e e-mail transacional no Render.
- [ ] Validar webhook Asaas real em sandbox/produção controlada.
- [ ] Validar login Google web e Android.
- [ ] Validar PWA após deploy limpando cache/instalando novamente.

Hardening recomendado pós-go-live:

- Remover `unsafe-inline` da CSP.
- Migrar `@app.on_event` para lifespan.
- Trocar `datetime.utcnow()` por datetimes timezone-aware.
- Adicionar revogação server-side de sessões.
- Criar teste de concorrência para finalização/repasse.
- Criar testes com Redis real e PostgreSQL real.
- Remover ou isolar módulos backend legados.

## 15. Conclusão

As correções V3-H01, V3-H02 e V3-H03 foram efetivas no código revisado. A suíte automatizada está verde com 16 testes. O sistema está pronto para uma rodada final de staging/preprodução.

A produção com pagamento real deve aguardar validação operacional de Redis, Alembic em PostgreSQL real e build Android, porque esses pontos dependem de infraestrutura não disponível integralmente nesta auditoria local.

