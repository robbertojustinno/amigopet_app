# AUDITORIA AMIGOPET V3

Data: 2026-07-09  
Escopo: reanálise completa após as correções C-01 a C-08, regressões R-01 a R-03 e prioridades P1 a P15.  
Modo de execução: auditoria estática e dinâmica sem alteração de código/configuração. Única escrita intencional: este relatório.

## 1. Resumo executivo

O projeto evoluiu de forma relevante desde a auditoria V2. Os achados críticos C-01 a C-08 foram mitigados no backend ativo `backend.app.main`: as rotas de negócio passaram a exigir sessão, papel correto, propriedade/participação no passeio; criação pública de admin foi bloqueada; endpoints administrativos foram protegidos; WebSocket passou a autenticar usuário; respostas foram reduzidas por contexto; o webhook Asaas ficou mais rígido; e os fluxos quebrados de cadastro/login foram recompostos.

Os testes automatizados atuais passaram:

```text
python -m pytest
12 passed, 144 warnings in 8.68s
```

Apesar disso, ainda há riscos relevantes antes de produção. Os principais bloqueadores são:

1. APKs Android ainda apontam para URL fixa do Render (`amigopet-6td8.onrender.com`), o que dificulta domínio próprio, staging e troca segura de ambiente.
2. A finalização de passeio pode tentar novo repasse Asaas em chamadas repetidas se o repasse anterior ficou `solicitado`, `pending` ou outro estado intermediário com `payout_transfer_id`.
3. O rate limit é local em memória; em produção com múltiplas instâncias ele não é global e pode ser contornado por distribuição de tráfego/restart.

Conclusão: o sistema está significativamente mais seguro que na V2, mas ainda não deve ser promovido a produção com pagamento real e escala multi-instância sem tratar os achados `V3-H01`, `V3-H02` e `V3-H03`, além de validar migração Alembic contra cópia do banco real.

## 2. Verificações executadas

Comandos principais:

- `python -m pytest`
- `rg` em backend, frontend, Android, migrations e deploy para autenticação/autorização, URLs fixas, seeds, DDL, CSP, SRI, CSRF, WebSocket, DTOs, innerHTML e código legado.
- Leitura direcionada de:
  - `backend/app/main.py`
  - `frontend/app.js`
  - `frontend/walker.js`
  - `frontend/admin.html`
  - `frontend/sw.js`
  - `frontend/config.js`
  - `cliente/src/main/java/.../MainActivity.java`
  - `passeador/src/main/java/.../MainActivity.java`
  - manifests Android
  - `render.yaml`
  - `Procfile`
  - `backend/Dockerfile`
  - `backend/start.sh`
  - `alembic.ini`
  - `migrations/env.py`
  - `migrations/versions/20260709_0001_initial_schema.py`
  - `tests/test_security_flows.py`

## 3. Status dos achados críticos C-01 a C-08

| Achado | Status V3 | Evidência / observação |
|---|---:|---|
| C-01 - Ausência generalizada de autorização nas APIs | Eliminado no fluxo ativo | Rotas de pets, passeios, pagamentos, mensagens, notificações e admin usam dependências de usuário autenticado, papel e participação/propriedade. |
| C-02 - Tomada de conta via `/api/auth/google/session/{user_id}` | Eliminado | Endpoint inseguro não aparece mais no fluxo ativo; login Google preservado por callback/sessão. |
| C-03 - Criação pública arbitrária de admin | Eliminado | Cadastro público cria cliente; cadastro de passeador tem fluxo próprio seguro; admin não é aceito por endpoint público. |
| C-04 - `/api/admin/pricing` e `/api/admin/payout-settings` públicos | Eliminado | Endpoints exigem admin autenticado. |
| C-05 - Credenciais padrão/reset automático no startup | Mitigado | `seed_data()` retorna em produção e não recria admin/senha 123456. Ainda há seed de configurações padrão no import; ver `V3-M02`. |
| C-06 - Operações financeiras/estado dos passeios sem participação correta | Mitigado | Aceitar/rejeitar/iniciar/finalizar/localização/sync exigem usuário correto. Risco remanescente específico de idempotência de repasse em `finish`; ver `V3-H02`. |
| C-07 - Exposição excessiva de dados pessoais/financeiros | Mitigado | DTOs por contexto foram introduzidos para cliente, passeador, público e admin. Ainda há necessidade de revisão contínua conforme novos campos forem adicionados. |
| C-08 - WebSocket sem autenticação/autorização | Eliminado no escopo atual | WebSocket exige sessão por cookie e eventos são roteados por participação/papel. Redis pub/sub é opcional para múltiplas instâncias. |

## 4. Status das prioridades V2 P1 a P15

| Item | Status V3 | Observação |
|---|---:|---|
| P1 - `SESSION_SECRET` inseguro | Implementado | Produção falha se segredo estiver ausente/fraco; sem fallback para Google/Asaas. |
| P2 - CORS permissivo com credenciais | Implementado | Produção exige `CORS_ORIGINS` explícito sem wildcard. |
| P3 - Rate limiting | Parcial | Implementado em memória. Falta backend distribuído para produção multi-instância; ver `V3-H03`. |
| P4 - Hash bcrypt/Argon2id | Implementado | Compatibilidade com SHA-256 legado e rehash no login. |
| P5 - CSRF | Implementado | Cookie + header em rotas autenticadas que alteram estado. |
| P6 - DTOs mínimos | Implementado | Redução por contexto aplicada em usuários/passeios/mensagens/eventos. |
| P7 - WebSocket Redis-ready | Implementado | Redis pub/sub opcional com fallback em memória. |
| P8 - Webhook Asaas hardening | Implementado | Valida token, consulta Asaas, payment id, referência, valor, moeda/customer quando disponível e idempotência de confirmação. |
| P9 - Legado duplicado | Parcial | Backups/patches ativos removidos. Ainda há módulos antigos não usados em `backend/app/{core,db,models,schemas,services}`; ver `V3-M04`. |
| P10 - URLs fixas Render no frontend | Implementado no frontend web | Frontend web deriva de `location.origin`/config. Android ainda tem URL fixa; ver `V3-H01`. |
| P11 - Cabeçalhos segurança/SRI | Implementado com ressalva | Headers existem e Leaflet usa SRI. CSP mantém `unsafe-inline` por dependência de scripts/handlers inline; ver `V3-M01`. |
| P12 - `innerHTML` | Implementado com ressalva | Uso centralizado em sanitizadores (`sanitizeHtml`/`setSafeHTML`). Manter padrão obrigatório em novas telas. |
| P13 - Admin session real | Implementado | Admin valida `/api/auth/session/current` no carregamento e limpa localStorage se sessão expirar. |
| P14 - Alembic | Implementado com ressalva | Startup não executa DDL improvisado. Migração roda no start do web process; ver `V3-M03`. |
| P15 - Testes automatizados | Implementado | 12 testes cobrindo fluxos críticos. Falta ampliar para Android/E2E/carga/concorrência financeira. |

## 5. Achados remanescentes antes de produção

### V3-H01 - APKs Android usam URL fixa do Render

Severidade: Alta  
Arquivos evidenciados:

- `cliente/src/main/java/com/rovix/amigopet/cliente/MainActivity.java`
- `passeador/src/main/java/com/rovix/amigopet/passeador/MainActivity.java`

Os apps Android ainda usam `https://amigopet-6td8.onrender.com` diretamente. O app do passeador também chama diretamente endpoints Google nesse host.

Impacto:

- APK publicado fica preso ao ambiente Render atual.
- Domínio próprio, staging, rollback, blue/green deploy e troca emergencial de host exigem novo build/distribuição.
- O P10 foi resolvido para frontend web, mas não para Android.

Recomendação:

- Mover URL base para `BuildConfig`/flavors (`dev`, `staging`, `prod`) ou configuração remota assinada.
- Bloquear navegação WebView para hosts permitidos.
- Regerar APKs por ambiente.

### V3-H02 - Finalização de passeio pode duplicar solicitação de repasse

Severidade: Alta  
Arquivo evidenciado: `backend/app/main.py`, função `finish_walk`.

A função evita novo repasse apenas quando:

```text
payout_status == "pago" && payout_transfer_id existe
```

Se uma chamada anterior criou transferência e deixou `payout_status` como `solicitado`, `pending`, `processing` ou equivalente com `payout_transfer_id`, uma nova chamada a `/api/walks/{id}/finish` pode tentar novo `create_asaas_pix_transfer_to_walker`.

Impacto:

- Risco financeiro de repasse duplicado ao passeador.
- Repetição de mensagens/eventos de passeio finalizado.

Recomendação:

- Tornar `finish_walk` idempotente.
- Bloquear nova transferência quando `payout_transfer_id` já existir, independentemente de status, exceto fluxo administrativo explícito de retry.
- Salvar chave de idempotência por passeio/repasse, se Asaas suportar.
- Adicionar teste automatizado de dupla chamada de finalização.

### V3-H03 - Rate limiting em memória não protege ambiente multi-instância

Severidade: Alta em produção escalada; Média em instância única  
Arquivo evidenciado: `backend/app/main.py`, funções de rate limit.

O rate limit atual usa estado local do processo. Isso é simples e funciona em instância única, mas não é global.

Impacto:

- Ataques de login, reset, cadastro, pedidos e webhooks podem contornar limites distribuindo requisições entre instâncias.
- Reinício limpa contadores.

Recomendação:

- Usar Redis para rate limit, preferencialmente o mesmo `REDIS_URL` já previsto para WebSocket.
- Definir limites por IP, usuário, e-mail e escopo, com TTL atômico.
- Manter fallback em memória apenas para desenvolvimento local.

### V3-M01 - CSP ainda depende de `unsafe-inline`

Severidade: Média  
Arquivo evidenciado: `backend/app/main.py`.

A CSP contém:

```text
script-src 'self' 'unsafe-inline' https://unpkg.com
style-src 'self' 'unsafe-inline' https://unpkg.com
```

Isso preserva o frontend atual, mas reduz o ganho de CSP contra XSS.

Impacto:

- Se algum ponto de injeção HTML escapar da sanitização, `unsafe-inline` facilita execução de script.

Recomendação:

- Remover handlers inline e scripts inline do HTML.
- Migrar lógica para arquivos JS versionados.
- Usar nonce/hash por resposta ou CSP sem inline.

### V3-M02 - Seeds/configurações ainda executam no import da aplicação

Severidade: Média  
Arquivo evidenciado: `backend/app/main.py`.

`seed_data()` foi neutralizado em produção para credenciais padrão, mas `seed_pricing_settings()` e `seed_payout_settings()` ainda executam durante import.

Impacto:

- Import da aplicação continua causando escrita no banco.
- Se Alembic não tiver rodado, startup pode falhar.
- Processo de configuração fica implícito e menos auditável.

Recomendação:

- Mover inicialização de configurações para comando explícito de seed/admin ou migration data controlada.
- Em produção, exigir configuração administrativa explícita ou seed idempotente executado em etapa de deploy controlada.

### V3-M03 - Alembic roda no start do web process

Severidade: Média  
Arquivos evidenciados: `render.yaml`, `Procfile`, `backend/Dockerfile`, `backend/start.sh`.

O deploy roda `alembic upgrade head` antes de iniciar o servidor. Isso removeu o DDL improvisado do startup, mas ainda acopla migração ao processo web.

Impacto:

- Em deploy com múltiplas instâncias, mais de um processo pode tentar migrar.
- Falhas de migração derrubam a aplicação em vez de falharem numa etapa de release separada.
- A migração inicial faz normalização permissiva de colunas legadas, incluindo `DROP NOT NULL` em colunas de `walk_requests` no PostgreSQL para preservar compatibilidade.

Recomendação:

- Usar etapa de release/predeploy dedicada no Render, ou job manual obrigatório.
- Ensaiar `alembic upgrade head` em cópia recente do banco de produção.
- Criar plano de rollback e backup antes da primeira execução em produção.
- Adicionar testes de migração contra PostgreSQL real/staging, não apenas SQLite.

### V3-M04 - Backend ativo permanece monolítico e há módulos legados não usados

Severidade: Média  
Evidência:

- App ativo: `backend.app.main`
- Pastas ainda existentes: `backend/app/core`, `backend/app/db`, `backend/app/models`, `backend/app/schemas`, `backend/app/services`

O P9 removeu backups/patches conflitantes, mas o backend ainda concentra modelos, schemas, regras, rotas, WebSocket, pagamento, seeds e static serving em um único arquivo grande. Também restam módulos modulares antigos que não parecem participar do deploy ativo.

Impacto:

- Maior risco de regressão em mudanças futuras.
- Dificulta revisão de segurança por domínio.
- Módulos não usados podem confundir manutenção e onboarding.

Recomendação:

- Planejar extração incremental por domínio: auth, users, pets, walks, payments, websocket, admin.
- Remover ou arquivar módulos legados apenas após cobertura de testes e confirmação de não uso.

### V3-M05 - Webhook Asaas depende de token compartilhado e consulta externa

Severidade: Média  
Arquivo evidenciado: `backend/app/main.py`.

O webhook foi endurecido e agora rejeita confirmação quando não consegue validar no Asaas. Ainda assim, a autenticação principal observada é token compartilhado em header.

Impacto:

- Vazamento do token permite chamadas forjadas até rotação.
- Sem assinatura por payload/timestamp, a proteção contra replay depende de idempotência e validação externa.

Recomendação:

- Se Asaas disponibilizar assinatura HMAC/timestamp/IP allowlist, implementar.
- Rotacionar `ASAAS_WEBHOOK_TOKEN`.
- Registrar somente dados mínimos em logs.

### V3-M06 - WebView Android permite navegação externa ampla

Severidade: Média  
Arquivos evidenciados:

- `cliente/.../MainActivity.java`
- `passeador/.../MainActivity.java`

Os apps usam WebView com JavaScript habilitado, necessário para o frontend. A navegação externa é tratada, mas a base fixa e a permissão de abrir HTTP/HTTPS externo devem ser revisadas com allowlist estrita.

Impacto:

- Redirecionamentos indevidos podem abrir superfícies externas.
- Segurança efetiva depende do conteúdo servido pelo host fixo.

Recomendação:

- Definir allowlist de domínios internos e provedores necessários.
- Abrir domínios externos no browser do sistema, não dentro do WebView, quando aplicável.
- Revisar `allowBackup="true"` antes de publicação em loja.

### V3-M07 - PWA pode servir shell antigo em cenários offline/cache

Severidade: Média/Baixa  
Arquivo evidenciado: `frontend/sw.js`.

O service worker ignora `/api` e `/ws`, e usa `no-store` para JS/CSS, o que é positivo. Ainda assim, HTML e app shell são cacheados e podem manter UI antiga até atualização completa do cache.

Impacto:

- Usuário pode ver frontend antigo após deploy, especialmente offline/intermitente.
- Em mudanças de contrato API/frontend, isso pode gerar erros temporários.

Recomendação:

- Versionar cache por build.
- Exibir prompt de atualização quando novo service worker ativar.
- Considerar não cachear HTML autenticado/admin.

### V3-L01 - Arquivos frontend duplicados na raiz podem divergir do frontend ativo

Severidade: Baixa  
Evidência:

- `frontend/app.js`, `frontend/index.html`, `frontend/styles.css`
- `app.js`, `index.html`, `styles.css` na raiz

O backend ativo serve `frontend/`, mas cópias na raiz ainda existem.

Impacto:

- Confusão em manutenção.
- Risco de deploy incorreto por ferramenta que use raiz como static dir.

Recomendação:

- Documentar explicitamente que `frontend/` é a origem ativa.
- Remover ou isolar duplicatas em tarefa própria, com validação de deploy.

### V3-L02 - Warnings de depreciação acumulados nos testes

Severidade: Baixa  
Evidência: `python -m pytest` retornou 144 warnings.

Principais avisos:

- `FastAPI @app.on_event("startup")` depreciado em favor de lifespan handlers.
- `datetime.utcnow()` depreciado no Python 3.12 para uso futuro; preferir timezone-aware.

Impacto:

- Não bloqueia produção hoje.
- Pode virar falha em atualizações futuras de Python/FastAPI.

Recomendação:

- Migrar startup para lifespan.
- Trocar timestamps para `datetime.now(datetime.UTC)` ou helper central.
- Configurar CI para falhar em warnings novos após limpeza.

### V3-L03 - `.env.example` está incompleto/desatualizado

Severidade: Baixa/Média  
Arquivo evidenciado: `.env.example`.

O arquivo contém apenas:

```text
SECRET_KEY=troque-essa-chave-em-producao
DATABASE_URL=sqlite:///./amigopet.db
APP_NAME=AmigoPet Pro
```

Mas a aplicação atual depende de variáveis como `SESSION_SECRET`, `CORS_ORIGINS`, `ENVIRONMENT`, `ASAAS_API_KEY`, `ASAAS_WEBHOOK_TOKEN`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `PUBLIC_BASE_URL`, `REDIS_URL` e outras.

Impacto:

- Risco de deploy incompleto.
- Onboarding e staging ficam sujeitos a tentativa/erro.

Recomendação:

- Atualizar `.env.example` com todas as variáveis atuais, marcando obrigatórias em produção.
- Incluir exemplos seguros sem segredos reais.

## 6. Backend

Pontos positivos:

- Autorização centralizada por dependências.
- Sessão HMAC com segredo obrigatório forte em produção.
- CSRF aplicado a mutações autenticadas por cookie.
- CORS produtivo exige origens explícitas.
- Hash de senha com bcrypt e rehash de legado SHA-256.
- Webhook Asaas não confirma pagamento sem validação externa.
- WebSocket autenticado e preparado para Redis.
- Testes automatizados cobrem regressões críticas.

Riscos principais:

- Monólito operacional grande em `backend/app/main.py`.
- Rate limit local.
- Idempotência de repasse na finalização precisa ser fortalecida.
- Seeds de configurações no import.
- Sessões são stateless; logout remove cookie local, mas não há revogação server-side de sessão roubada até expiração/rotação do segredo.

Recomendação de produção:

- Resolver `V3-H02` e `V3-H03`.
- Adicionar server-side session store ou lista de revogação se o risco operacional exigir.
- Criar testes de concorrência para finalizar passeio/pagamento.

## 7. Frontend web

Pontos positivos:

- URLs Render removidas do frontend web; API/WS derivam de `location.origin` ou configuração.
- Uso de sanitização centralizada para HTML dinâmico.
- Admin valida sessão real no carregamento.
- SRI aplicado ao Leaflet.
- Service worker evita cache de API/WS.

Riscos:

- CSP ainda permite inline.
- `localStorage` continua usado como cache de conveniência de usuário; o código valida sessão real, mas dados locais devem continuar sendo tratados como não confiáveis.
- Duplicatas na raiz podem causar divergência se servidas por engano.

## 8. Android

Pontos positivos:

- `usesCleartextTraffic="false"`.
- Apps carregam HTTPS.
- Fluxo WebView preserva frontend web.

Riscos:

- URL fixa do Render.
- Ausência de flavors/configuração por ambiente.
- `allowBackup="true"` deve ser revisto para produção.
- WebView com JavaScript é esperado, mas exige allowlist rígida e cuidado com navegação externa.

## 9. PWA

Pontos positivos:

- Manifest e service worker existem.
- API/WS não são cacheados.
- JS/CSS usam estratégia `no-store` com fallback.

Riscos:

- HTML/app shell pode ficar antigo após deploy.
- Não há fluxo visível de atualização obrigatória para usuário.
- Mudanças incompatíveis entre frontend/API podem gerar erros temporários até o cache atualizar.

## 10. Deploy, Render e configuração

Pontos positivos:

- `render.yaml`, `Procfile`, Dockerfile e `start.sh` apontam para `backend.app.main`.
- Alembic roda antes do servidor.
- Produção falha sem `SESSION_SECRET` forte e `CORS_ORIGINS`.

Riscos:

- Migração acoplada ao start do web process.
- `.env.example` não reflete a aplicação atual.
- APKs não acompanham domínio/configuração por ambiente.
- Redis é opcional; sem Redis, WebSocket e rate limit têm limitações em escala.

Checklist mínimo para Render produção:

- `ENVIRONMENT=production`
- `SESSION_SECRET` aleatório com pelo menos 32 caracteres
- `CORS_ORIGINS=https://dominio-oficial`
- `DATABASE_URL` PostgreSQL
- `ASAAS_API_KEY`
- `ASAAS_WEBHOOK_TOKEN`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `PUBLIC_BASE_URL=https://dominio-oficial`
- `REDIS_URL` se houver múltiplas instâncias ou necessidade de WebSocket escalável
- Executar `alembic upgrade head` em staging antes de produção

## 11. Alembic

Status: estrutura profissional criada e DDL improvisado removido do startup.

Riscos:

- `target_metadata = None`; autogenerate não está configurado. Isso é aceitável para migrations manuais, mas exige disciplina.
- Migração inicial é idempotente e compatível com legado, porém permissiva para `walk_requests`.
- Falta evidência de teste contra PostgreSQL real com dados de produção.

Recomendação:

- Criar banco staging com dump sanitizado.
- Rodar `alembic upgrade head`.
- Validar índices, constraints, nulos e dados financeiros.
- Documentar processo de criação de novas migrations.

## 12. Testes automatizados

Status atual:

```text
12 passed
```

Cobertura observada:

- Autenticação e sessão.
- Bloqueio de criação pública de admin.
- Endpoints admin protegidos.
- CSRF.
- Rate limit.
- Propriedade de pets.
- Visibilidade e operações de passeios.
- DTOs e exposição de dados.
- Webhook Asaas.
- WebSocket autenticado.
- Admin panel com validação de sessão.

Lacunas:

- Teste de idempotência de finalização/repasse.
- Testes de concorrência.
- Testes contra PostgreSQL.
- Testes E2E browser/PWA.
- Testes Android instrumentados.
- Testes de Redis pub/sub real.
- Testes de CSP em browser.

## 13. Decisão de prontidão

Classificação atual: **não pronto para produção com pagamento real sem correções adicionais de alto impacto**.

Bloqueadores recomendados:

1. Corrigir idempotência de repasse na finalização (`V3-H02`).
2. Tornar rate limit distribuído com Redis para produção multi-instância (`V3-H03`) ou garantir instância única com proteção de borda.
3. Remover URLs fixas do Android e gerar APKs por ambiente/domínio (`V3-H01`).
4. Ensaiar Alembic em staging com cópia sanitizada do banco real.
5. Atualizar `.env.example` e runbook de deploy.

Após esses pontos, o risco remanescente cai para hardening evolutivo: CSP sem inline, modularização do backend, limpeza de legado, melhorias de PWA e ampliação de testes.

