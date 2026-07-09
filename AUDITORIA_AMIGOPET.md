# Auditoria técnica do AmigoPet

**Data:** 08/07/2026  
**Escopo:** frontend web/PWA, backend FastAPI, wrappers Android, configuração de deploy, banco, integrações e experiência do usuário.  
**Método:** revisão estática integral dos arquivos-fonte e configurações, busca de padrões de risco, comparação de artefatos duplicados e validação sintática com `compileall` e `node --check`. Não foram feitas chamadas ao ambiente de produção nem testes destrutivos.

## Resumo executivo

O sistema **não está pronto para produção**. A aplicação ativa (`backend/app/main.py`) tem autenticação por cookie, mas quase nenhuma rota de negócio usa essa identidade. Em vez disso, confia em IDs enviados pelo navegador. Isso permite acesso e alteração horizontal de contas, pedidos, mensagens, localização, carteira e configurações administrativas. Há também tomada de conta direta pelo endpoint de sessão Google, criação arbitrária de administradores e credenciais padrão recriadas no startup.

Além dos riscos críticos, o repositório contém duas arquiteturas de backend concorrentes, migrações manuais que ignoram falhas, frontend monolítico e duplicado, contratos divergentes entre cliente e servidor, dependências sem versão, ausência de testes e observabilidade insuficiente. Corrigir apenas a interface não mitiga os riscos: a autorização precisa ser centralizada no servidor antes de qualquer lançamento.

### Contagem de achados

| Severidade | Quantidade |
|---|---:|
| Crítica | 8 |
| Alta | 13 |
| Média | 15 |
| Baixa | 7 |

## Achados críticos

### C-01 — Ausência generalizada de autorização nas APIs

**Evidência:** apenas `/api/auth/session/current` consulta `session_user_from_request` (`backend/app/main.py:1548-1553`). As rotas de usuários, termos, passeadores, pets, pedidos, mensagens, notificações, avaliações e carteira recebem IDs do cliente e não validam o usuário da sessão (`1634-1778`, `1825-2439`).

**Impacto:** qualquer pessoa pode enumerar e modificar dados de outros usuários, aceitar termos em nome deles, criar pets/pedidos, ler chats, marcar notificações, consultar carteira e operar passeios. É uma falha sistêmica de BOLA/IDOR.

**Correção:** criar dependências `current_user`, `require_role` e verificações de propriedade/participação; nunca tomar identidade de `client_id`, `sender_id`, `rater_id`, `walker_id` ou `user_id` enviados pelo corpo/query. Derivar esses valores da sessão.

### C-02 — Tomada de conta pelo endpoint Google

**Evidência:** `GET /api/auth/google/session/{user_id}` busca qualquer usuário pelo ID, devolve seus dados e cria cookie autenticado para ele, sem validar OAuth ou sessão (`backend/app/main.py:1538-1546`). O frontend usa diretamente essa rota (`frontend/app.js:519`, `frontend/walker.js:198`).

**Impacto:** acessar `/api/auth/google/session/1`, `/2`, etc. autentica o atacante como a vítima, inclusive administrador.

**Correção:** remover a rota pública. No callback OAuth, gerar código de uso único, curto e vinculado a state/PKCE; ou estabelecer a sessão diretamente e redirecionar sem expor ID autenticável.

### C-03 — Criação arbitrária de usuário administrador

**Evidência:** `RegisterIn.role` é controlado pelo cliente (`backend/app/main.py:237`) e `/api/auth/register` persiste todo o payload sem lista de papéis permitidos (`1403-1413`).

**Impacto:** cadastro com `"role":"admin"` cria administrador. Mesmo que a UI não ofereça a opção, a API aceita.

**Correção:** cadastro público deve fixar `role=client`; cadastro/aprovação de passeador deve ter fluxo próprio; criação de admin somente por processo administrativo autenticado ou provisioning seguro.

### C-04 — Configurações administrativas públicas

**Evidência:** `/api/admin/pricing` e `/api/admin/payout-settings` não exigem autenticação nem papel admin (`backend/app/main.py:1793-1822`).

**Impacto:** qualquer atacante pode zerar preços ou redirecionar a divisão financeira para 0/100, afetando cobranças e repasses.

**Correção:** exigir admin, registrar auditoria imutável, usar controle de concorrência e validar faixas comerciais, não apenas soma igual a 100.

### C-05 — Credenciais padrão e reset de senhas no startup

**Evidência:** `seed_data()` cria administrador e contas de demonstração e define/redefine suas senhas como `123456` (`backend/app/main.py:1079-1095`); a função roda na importação/startup (`1373`). `frontend/admin.html:64` ainda preenche a senha `123456`.

**Impacto:** credenciais conhecidas em produção e possível reversão recorrente da senha dessas contas após deploy/restart.

**Correção:** remover seed de produção; separar fixture de desenvolvimento; criar admin inicial via comando explícito e segredo efêmero, exigindo troca no primeiro acesso.

### C-06 — Operações financeiras e de estado sem autorização

**Evidência:** aceitar/rejeitar/iniciar/finalizar passeio e atualizar localização usam apenas `walk_id`/`walker_id` informados (`backend/app/main.py:1948-1976`, `2106-2186`). Finalizar pode disparar repasse (`2121-2168`). Sincronização de pagamento também é pública (`2081-2103`).

**Impacto:** alteração fraudulenta do ciclo do pedido, falsificação de GPS, conclusão indevida e possível acionamento de repasses.

**Correção:** autorizar participante e transição de máquina de estados dentro de transação; tornar callbacks financeiros idempotentes; bloquear transições incompatíveis e registrar ator/antes/depois.

### C-07 — Exposição massiva de dados pessoais e financeiros

**Evidência:** `/api/users` retorna todos os usuários e `user_to_dict` inclui telefone, endereço, documento, chave PIX, documento do titular, IP de aceite e demais dados (`backend/app/main.py:459-477`, `1634-1640`). `/api/walks`, mensagens, notificações e carteiras também são enumeráveis.

**Impacto:** vazamento de PII e dados financeiros, risco físico a clientes/passeadores e grave exposição LGPD.

**Correção:** DTOs por contexto com minimização de dados; consulta pública de passeadores deve expor somente perfil necessário; criptografar campos sensíveis; política de retenção, consentimento, direitos do titular e trilha de acesso.

### C-08 — WebSocket público transmite eventos entre todos os usuários

**Evidência:** `/ws` aceita sem autenticação e `ConnectionManager` mantém uma lista global; typing e eventos são transmitidos a todos (`backend/app/main.py:304-329`, `1378-1397`). Frontends conectam sem token/handshake de sala.

**Impacto:** espionagem de metadados, IDs e atualizações de pedidos/localização; falsificação de eventos de digitação; consumo ilimitado de conexões.

**Correção:** autenticar no handshake pelo cookie, associar conexões a usuário e salas autorizadas por pedido, validar payload, limitar mensagem/conexão e usar broker pub/sub para múltiplas instâncias.

## Achados altos

### A-01 — Senhas com hash inadequado

`hash_password` usa SHA-256 salgado de uma única rodada (`backend/app/main.py:388-401`). É rápido demais contra força bruta offline. Usar Argon2id ou bcrypt via biblioteca mantida, com migração no login. Exigir senha maior e checar senhas comprometidas.

### A-02 — Segredo de sessão previsível e sessão longa

`SESSION_SECRET` cai para segredo fixo ou reutiliza segredo Google/Asaas (`backend/app/main.py:56-62`); cookie dura 180 dias e não possui revogação (`54-55`, `404-442`). Falhar o startup sem segredo dedicado forte, reduzir duração, rotacionar, guardar versão/nonce no servidor e revogar em troca de senha/bloqueio.

### A-03 — OAuth sem proteção CSRF real

O parâmetro OAuth `state` contém apenas o papel (`backend/app/main.py:1431-1454`), sem nonce vinculado ao navegador. Isso permite login CSRF/confusão de sessão. Usar `state` aleatório, uso único, SameSite adequado e PKCE; validar issuer, audience, nonce e e-mail verificado.

### A-04 — Sem rate limiting ou bloqueio adaptativo

Login, cadastro, reset de senha, Google session, WebSocket e criação de cobranças não têm limite. O código de reset tem seis dígitos e nenhuma contagem de tentativas (`1563-1631`). Aplicar limites por IP/conta/dispositivo, backoff, CAPTCHA onde apropriado e invalidar código após tentativas.

### A-05 — Webhook pode ficar sem autenticação

`validate_asaas_webhook_token` aceita qualquer requisição quando `ASAAS_WEBHOOK_TOKEN` está vazio (`backend/app/main.py:817-823`). As três URLs chegam ao mesmo handler (`2015-2018`). Em produção, configuração ausente deve falhar fechada; validar assinatura/token, origem conforme documentação, payload, valor/moeda/referência e idempotência.

### A-06 — CORS inseguro/incompatível

O padrão é `allow_origins=["*"]` com `allow_credentials=True` (`backend/app/main.py:72-78`). Além de perigoso conceitualmente, wildcard com credenciais é incompatível com navegadores. Manter allowlist exata por ambiente e rejeitar configuração curinga em produção.

### A-07 — CSRF em APIs autenticadas por cookie

As requisições mutáveis não têm token CSRF nem validação de `Origin`; `SameSite=Lax` reduz, mas não substitui a defesa, especialmente com CORS/configurações futuras. Implementar token CSRF ou padrão same-origin rigoroso com validação de Origin/Referer.

### A-08 — Contratos frontend/backend quebrados

O frontend chama `/api/auth/verify-code` e `/api/auth/resend-code` (`frontend/app.js:610,631`), inexistentes em `main.py`. Os apps Android chamam `/api/auth/google/android-config` e `/api/auth/google/android` (ambos `MainActivity.java:171,215`), também inexistentes. Resultado: verificação de cadastro e login Google Android falham em execução.

### A-09 — Migração de banco insegura

O backend executa DDL extenso no import/startup e captura erros genericamente (`backend/app/main.py:1129-1373`); existe ainda outro migrador manual (`backend/app/db/migrations.py`). Isso mascara schema parcialmente aplicado, cria corrida entre workers e dificulta rollback. Adotar Alembic, migrations versionadas e etapa única de deploy.

### A-10 — Duas APIs concorrentes e modelos incompatíveis

`backend/app/main.py` redefine app/modelos/rotas em arquivo de 105 KB, enquanto `backend/app/api/routes.py`, `models/`, `schemas/`, `services/` implementam outra API não incluída pelo app ativo. Há nomes incompatíveis como `password_hash` versus `password`, `dogs_count` versus `dog_count`, e endpoints diferentes. Isso aumenta correções no lugar errado e drift de banco. Escolher uma arquitetura e remover/arquivar a outra.

### A-11 — Fluxo financeiro sem garantias transacionais suficientes

Criação de pedido faz vários commits antes/depois da API externa (`backend/app/main.py:1870-1920`), e conclusão/repasse também mistura banco e rede. Falhas deixam estados intermediários. Usar idempotency keys, outbox/jobs, constraints únicas para IDs externos, locks/controle otimista e reconciliação periódica.

### A-12 — Upload/fotos em base64 sem limites

Fotos são strings/Text enviadas no JSON e guardadas no banco; a checagem do pet exige apenas comprimento mínimo (`backend/app/main.py:1768-1779`). Isso permite payloads enormes, conteúdo ativo/URL maliciosa e crescimento do banco. Validar MIME por bytes, limitar tamanho/dimensões, reprocessar imagem e usar object storage com URLs assinadas.

### A-13 — Android WebView aceita navegação ampla e acesso a arquivos

JavaScript, DOM storage, file access e content access estão habilitados (`cliente/.../MainActivity.java:72-77` e equivalente do passeador). O `WebViewClient` carrega URLs sem allowlist robusta (`85-148`), ampliando phishing e acesso local se houver navegação/injeção. Desabilitar acessos não necessários, restringir host/esquema, abrir externos fora do WebView, ativar Safe Browsing e desabilitar backup de dados sensíveis (`AndroidManifest.xml:10`).

## Achados médios

### M-01 — Dependências não reprodutíveis

`requirements.txt` e `backend/requirements.txt` não fixam versões/hashes; Gradle também depende de repositórios sem lockfile. Um deploy pode mudar sem alteração de código. Fixar versões, gerar lock/SBOM e automatizar auditoria de vulnerabilidades.

### M-02 — Configurações de deploy divergentes

Render instala o `requirements.txt` raiz e importa `backend.app.main`; Docker copia `backend/requirements.txt`, muda o diretório e inicia `app.main`; `start.sh`, Procfile e portas variam entre 8000/10000. O compose monta código sobre a imagem. Consolidar uma estratégia e adicionar health/readiness reais.

### M-03 — Health check superficial

`/health` sempre retorna OK sem verificar banco ou integrações (`backend/app/main.py:1399-1401`). Separar liveness/readiness e testar DB; não fazer chamadas lentas a terceiros na liveness.

### M-04 — Chamadas HTTP síncronas em rotas async

As rotas `async` usam `requests` síncrono com timeout de até 30 s, bloqueando o event loop durante Asaas/Google/Resend. Usar cliente async compartilhado, pools, timeouts separados, retries com jitter e circuit breaker/job queue.

### M-05 — Banco e conexão sem configuração operacional

`create_engine` não define `pool_pre_ping`, limites, reciclagem, timeout nem isolamento; SQLite é fallback de produção possível. Configurar pool PostgreSQL, limites compatíveis com o provedor e falhar se produção iniciar com SQLite.

### M-06 — Listagens sem paginação

Usuários, passeios, pets, mensagens, notificações e histórico retornam listas completas. Isso degrada banco, rede e DOM e facilita scraping. Implementar paginação cursor, limites máximos e índices orientados às consultas.

### M-07 — Frontend monolítico e duplicado

`app.js` (56 KB), `walker.js` (51 KB) e `main.py` concentram responsabilidades. `app.js`, `index.html` e `styles.css` da raiz são cópias byte a byte de `frontend/`. Há também `main_backup_google.py` e `backend_patch/`. Definir fonte canônica, modularizar e excluir artefatos históricos do pacote de deploy.

### M-08 — API e WebSocket fixos em produção

`frontend/app.js:1-2` e `walker.js:1-2` fixam o domínio Render. Isso quebra preview, desenvolvimento, domínio próprio e Docker local. Derivar de `location.origin` ou configuração injetada por ambiente.

### M-09 — XSS e URLs externas ainda têm superfícies frágeis

Há bom uso parcial de `escapeHtml`, mas grandes blocos usam `innerHTML`; URLs de foto/ticket são incorporadas em atributos. Sanitização HTML não equivale a validação de URL. Criar elementos pelo DOM, permitir somente `https:`/origens aprovadas, sanitizar atributos e adicionar CSP.

### M-10 — Sem cabeçalhos de segurança e SRI

Não há configuração explícita de CSP, HSTS, frame-ancestors/X-Frame-Options, Referrer-Policy ou Permissions-Policy. Leaflet é carregado do unpkg sem `integrity`. Configurar headers no servidor/proxy e preferir assets versionados locais ou SRI.

### M-11 — Service worker pode servir página errada

Para qualquer GET offline sem cache, `frontend/sw.js` cai em `/`, inclusive recursos/navegações do passeador; o install ignora falha de cache e ativa mesmo incompleto. Diferenciar navigation de assets, oferecer offline page e versionar/cachear atomicamente.

### M-12 — Dados de sessão duplicados no localStorage

Embora exista cookie HttpOnly, os objetos completos de usuário continuam no `localStorage` (`frontend/app.js`, `walker.js`, `admin.html`). XSS ou WebView comprometida lê PII e estado; a UI pode operar com papel/ID adulterado. Guardar somente estado não sensível e sempre reidratar identidade pelo servidor.

### M-13 — Observabilidade inadequada

Erros e dados de integrações usam `print`, alguns detalhes técnicos retornam ao cliente (`backend/app/main.py:1911-1918`), e exceções são silenciadas. Adotar logging estruturado com correlation ID, redaction, métricas, tracing e alertas; respostas públicas genéricas.

### M-14 — Concorrência e máquina de estados

Aceite de passeio não usa lock/compare-and-set; dois passeadores podem competir. Transições são atribuições livres de strings sem enum/constraint. Definir máquina de estados, `SELECT FOR UPDATE` ou update condicional, constraints e testes de concorrência.

### M-15 — Acessibilidade e UX de erro

Formulários dependem muito de placeholders, modais/menus não demonstram gestão consistente de foco/teclado e notificações toast não têm região live. Erros técnicos de terceiros chegam ao usuário e telas dependem de polling/WebSocket sem estados robustos. Adicionar labels associados, ARIA apenas quando necessário, foco, contraste testado, mensagens acionáveis, skeleton/empty/offline/retry e confirmação em ações financeiras.

## Achados baixos

### B-01 — Codificação de caracteres corrompida

Há mojibake em README, textos Python/Java e mensagens (`MagÃ©`, emojis quebrados). Padronizar UTF-8, configurar editor/CI e corrigir dados já persistidos.

### B-02 — Documentação e testes desatualizados

`backend/tests.http` testa `/api/users/register` e `/api/health`, mas o app ativo expõe `/api/auth/register` e `/health`. README descreve apenas WebViews. Criar documentação OpenAPI operacional e exemplos alinhados.

### B-03 — Ausência de suíte automatizada

Não existem testes unitários, integração, E2E, segurança ou carga; `tests.http` é somente coleção manual. Bloquear merge/deploy com testes de autorização, pagamentos/webhooks, estados, migrations e fluxos cliente/passeador/admin.

### B-04 — Sem CI/CD e verificações de qualidade visíveis

Não há workflow para lint, type-check, testes, secret scan, dependency scan, build Android ou smoke test. Implantar pipeline com ambientes e aprovação para produção.

### B-05 — Política de backup Android permissiva

`android:allowBackup="true"` nos dois apps pode incluir WebView/localStorage. Definir regras de data extraction/backup ou desabilitar backup para sessão e PII.

### B-06 — PWA usa SVG como ícone maskable/any

O manifest declara SVG com `purpose: any maskable`; suporte e safe zone variam. Gerar PNGs 192/512 e maskable dedicado, validar com ferramentas PWA.

### B-07 — Artefatos binários e jurídicos no repositório de aplicação

ZIPs, DOCX, PDFs, imagens de referência e patches aumentam clone/deploy e confundem origem. Mover documentação/binários para armazenamento/repositório apropriado; manter no pacote somente runtime necessário.

## Desempenho e escalabilidade

- O broadcast WebSocket é O(n), sequencial e em memória; não funciona corretamente com múltiplos workers/instâncias.
- Fotos base64 aumentam JSON e banco em aproximadamente 33%, além de impedir cache/CDN eficiente.
- Listagens completas e atualização frequente de DOM/mapa escalam mal.
- APIs externas bloqueiam workers e não têm fila de tarefas.
- Migrations e seeds no startup aumentam tempo de boot e risco em autoscaling.
- Não há cache HTTP, compressão configurada, lazy loading sistemático nem divisão de bundles.

## Arquitetura recomendada

1. Manter uma única aplicação FastAPI modular (`api`, `domain`, `repositories`, `services`) e uma única definição de modelos.
2. Centralizar autenticação/autorização por dependências e políticas; IDs de ator vêm da sessão.
3. Modelar passeio e pagamento como máquinas de estado transacionais, com outbox e workers para integrações.
4. Usar PostgreSQL + Alembic; Redis para rate limit, jobs e WebSocket/pub-sub, não como dependência silenciosamente opcional.
5. Separar DTO público, próprio e administrativo; criptografar/minimizar PII.
6. Modularizar frontend, usar configuração por ambiente e cliente API tipado a partir de OpenAPI.
7. Tratar Android como cliente hostil: nenhuma autorização pode depender do JavaScript/WebView.

## Plano de correção priorizado

### Antes de qualquer uso real (P0)

1. Tirar o ambiente público do ar ou restringi-lo enquanto C-01 a C-08 não forem corrigidos.
2. Remover `/api/auth/google/session/{user_id}`, impedir role arbitrário e eliminar seeds/senhas padrão.
3. Proteger todas as rotas com autenticação, papéis e propriedade; criar testes negativos para cada recurso.
4. Proteger admin, pagamentos, repasses, webhooks e WebSocket; rotacionar todos os segredos e sessões.
5. Revisar possível exposição já ocorrida: logs, usuários, termos, mensagens, localização e dados PIX; preparar resposta LGPD.

### Estabilização (P1)

1. Unificar backend e contratos; corrigir endpoints ausentes do web/Android.
2. Migrar senhas, banco e migrations; implementar rate limit, CSRF, headers e validação de uploads.
3. Tornar pagamentos idempotentes/transacionais e adicionar reconciliação.
4. Criar testes de integração/E2E e pipeline; fixar dependências.

### Qualidade e escala (P2)

1. Modularizar frontend/backend e remover duplicatas/legados.
2. Implementar paginação, object storage/CDN, jobs async e pub/sub.
3. Melhorar acessibilidade, offline/PWA, observabilidade, backups e documentação operacional.

## Critérios mínimos para liberação

- Teste automatizado prova que cliente A não lê/altera recursos de cliente B.
- Passeador só acessa pedidos destinados/disponíveis conforme regra e só opera pedido aceito por ele.
- Admin é autenticado, auditado e não pode ser criado pelo cadastro público.
- Webhook inválido não altera pagamento; callbacks repetidos são idempotentes.
- Nenhuma credencial padrão ou fallback de segredo inicia em produção.
- Migração limpa e upgrade de snapshot de produção passam em CI/staging.
- Dependências estão fixadas e sem vulnerabilidades críticas conhecidas.
- Fluxos web e Android contratualmente existentes passam E2E.
- Logs não contêm senha, token, chave PIX, documento ou payload sensível.
- Varredura DAST/SAST e revisão de autorização não apontam achado crítico/alto aberto.

## Verificações executadas e limitações

- `python -m compileall -q backend backend_patch`: aprovado.
- `node --check` em `frontend/app.js`, `walker.js`, `pwa.js` e `sw.js`: aprovado.
- Comparação SHA-256 confirmou duplicação exata de `app.js`, `index.html` e `styles.css` entre raiz e `frontend/`.
- Não foi possível validar comportamento real de Asaas, Google, Resend, PostgreSQL, Render ou domínio público sem executar chamadas externas e sem credenciais.
- Não foi realizado pentest ativo. Dado o nível das falhas de autorização, ele só deve ocorrer após a correção P0, em ambiente autorizado.
- A ausência de testes automatizados impede afirmar regressão funcional, compatibilidade entre versões ou capacidade de carga.

## Conclusão

O maior risco não é um bug isolado, mas o modelo de confiança: o servidor aceita identidade e autoridade informadas pelo cliente. A prioridade absoluta é reconstruir a fronteira de autorização e isolar operações financeiras. Depois disso, a consolidação arquitetural, migrations formais, testes e observabilidade tornam o produto sustentável. Até que os itens P0 estejam concluídos e verificados, o AmigoPet deve ser tratado como protótipo, não como sistema de produção.
