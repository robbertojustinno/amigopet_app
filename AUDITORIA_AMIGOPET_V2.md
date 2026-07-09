# AUDITORIA AMIGOPET V2

Data da reanálise: 2026-07-08  
Escopo: projeto local completo em `E:\amigopet_app`, considerando o estado atual após as correções C-01 a C-08.  
Regra aplicada: auditoria sem alteração de código-fonte. Este arquivo é o único artefato gerado.

## 1. Sumário executivo

As correções críticas C-01 a C-08 foram aplicadas no app FastAPI ativo (`backend/app/main.py`) e reduziram substancialmente a superfície explorável original. Não encontrei, no backend ativo, a mesma classe de falhas críticas abertas anteriormente: as rotas de negócio agora usam sessão, papel, propriedade e participação; a rota insegura de sessão Google foi removida; cadastro público não aceita mais `role`; configurações administrativas exigem admin; seeds não rodam em produção; operações financeiras/de estado exigem participante autorizado; `/api/users` expõe respostas mínimas; e o WebSocket exige sessão.

Ainda existem riscos relevantes para produção. Os principais não são os C-01 a C-08 originais, mas sim regressões funcionais e dívidas de segurança: cadastro público de passeador por e-mail ficou incompatível com a nova regra de cadastro apenas cliente; o app Android referencia endpoints Google nativos ausentes; há chamadas frontend para endpoints de verificação inexistentes; sessões dependem de segredo fallback fraco se variáveis não forem configuradas; CORS segue permissivo; não há rate limiting; senha usa SHA-256 simples em vez de KDF próprio para senhas; e há código legado duplicado com padrões inseguros fora do caminho de deploy.

Minha avaliação: o sistema está melhor que na auditoria anterior, mas ainda não está pronto para produção regulada/financeira sem hardening operacional, testes automatizados e remoção de legados.

## 2. Verificações executadas

Comandos executados com sucesso:

- `python -m py_compile backend\app\main.py`
- `node --check frontend\app.js`
- `node --check frontend\walker.js`
- Enumeração estática de rotas FastAPI por AST.
- Busca por padrões críticos: `google/session`, `google_user_id`, `manager.broadcast`, `Depends(get_current*)`, endpoints admin, seeds, `123456`, WebSocket, rotas Android/verify.

Limitação: não executei testes end-to-end reais contra banco/Asaas/Google, porque o projeto não tem suíte automatizada operacional para esses fluxos e integrações externas exigiriam credenciais.

## 3. Status dos achados críticos C-01 a C-08

| Achado | Status V2 | Evidência atual | Observação |
|---|---:|---|---|
| C-01 — Ausência generalizada de autorização | Eliminado no app ativo | Dependências `get_current_user`, `get_current_client`, `get_current_walker`, `get_current_admin` em `backend/app/main.py`; rotas de pets, walks, wallet, messages, notifications, ratings, admin e estados exigem sessão/papel. | Ainda há DTOs amplos para participantes/admin; isso é risco residual, não a falha original de ausência de autorização. |
| C-02 — Tomada de conta por `/api/auth/google/session/{user_id}` | Eliminado | Não há rota `google/session`; callback usa cookie de sessão e `/api/auth/session/current`. | Login Google web preservado. Android Google nativo ficou quebrado por endpoints ausentes, ver R-02. |
| C-03 — Criação arbitrária de admin no cadastro público | Eliminado | `/api/auth/register` exclui `role` do payload e persiste `role="client"`. | Regressão: cadastro de passeador por e-mail agora cria cliente, ver R-01. |
| C-04 — Admin pricing/payout públicos | Eliminado | `/api/admin/pricing` e `/api/admin/payout-settings` usam `Depends(get_current_admin)`. | `/api/pricing` continua público, coerente para cotação. |
| C-05 — Credenciais padrão e reset de senha no startup | Eliminado para produção | `seed_data()` retorna se `IS_PRODUCTION`; usuários existentes não têm mais `password_hash` redefinido. | Ainda há senha demo `123456` para desenvolvimento e preenchimento demo no frontend cliente/passeador; não recria admin em produção se `APP_ENV`/Render estiver correto. |
| C-06 — Operações financeiras/estado sem autorização | Eliminado no app ativo | `accept`, `reject`, `pay`, `sync`, `start`, `finish`, `location` exigem sessão e participação correta. | Cliente não consegue mais simular localização; isso é esperado pelo hardening. |
| C-07 — Exposição massiva de dados pessoais/financeiros públicas | Parcialmente eliminado / risco residual baixo-médio | `/api/users` público só retorna passeadores ativos via `public_walker_to_dict`; admin recebe lista reduzida. Rotas sensíveis exigem sessão. | Participantes/admin ainda recebem `walk_to_dict` com campos financeiros extensos. Não é público, mas merece DTO por contexto antes de produção. |
| C-08 — WebSocket público e broadcast global | Eliminado no app ativo | `/ws` valida cookie de sessão; `ConnectionManager` mapeia websocket por `user_id`; eventos de passeio usam `send_walk_event` para participantes/admin/passeadores autorizados. | Continua em memória e não escala entre múltiplas instâncias. |

## 4. Regressões detectadas após as correções

### R-01 — Cadastro de passeador por e-mail ficou incompatível

Severidade: alta funcional, baixa segurança.

`frontend/walker.js` ainda possui fluxo `registerWalker()` que envia `role: 'walker'` para `/api/auth/register`. A correção C-03 faz o backend ignorar `role` e criar sempre `client`. Resultado provável: um passeador que se cadastra por e-mail entra como cliente e é bloqueado pelas telas/rotas de passeador.

Impacto: onboarding de passeador por e-mail quebrado. Login/cadastro via Google para novo passeador ainda funciona porque `/api/auth/google/login/walker` preserva `role=walker` no callback.

Recomendação: criar fluxo separado e autenticado/aprovado para candidatura de passeador, por exemplo `/api/walkers/apply`, ou limitar UI a Google até existir aprovação admin.

### R-02 — Login Google nativo Android referencia endpoints ausentes

Severidade: alta funcional.

Os apps Android chamam:

- `/api/auth/google/android-config`
- `/api/auth/google/android`

Essas rotas não existem em `backend/app/main.py`. Isso aparece em `cliente/src/main/.../MainActivity.java` e `passeador/src/main/.../MainActivity.java`.

Impacto: Google Sign-In nativo nos APKs deve falhar. O login Google web dentro da WebView pode continuar funcionando se não for interceptado pelo código nativo; hoje o `WebViewClient` intercepta URLs contendo `/api/auth/google/login`, então a tendência é quebrar o login Google Android.

Recomendação: ou remover/interromper a interceptação nativa e deixar o OAuth web rodar, ou implementar endpoints nativos com verificação correta de `id_token`, emissão de cookie/token e separação segura por papel.

### R-03 — Frontend cliente chama endpoints de verificação inexistentes

Severidade: média funcional.

`frontend/app.js` chama:

- `/api/auth/verify-code`
- `/api/auth/resend-code`

Essas rotas não existem no app ativo. A verificação de e-mail/telefone parece incompleta ou remanescente de versão anterior.

Impacto: telas de verificação podem gerar erro para o usuário e criar estado de cadastro confuso.

Recomendação: remover UI morta ou implementar endpoints com rate limit e expiração.

### R-04 — Painel admin pode restaurar sessão apenas do `localStorage` sem validar no carregamento

Severidade: média funcional/UX, baixa segurança se backend permanece protegido.

`frontend/admin.html` lê `amigopet_admin_user` do `localStorage` e mostra dashboard se `role === 'admin'`. O backend bloqueia chamadas sensíveis sem cookie válido, então não é bypass real de autorização. Porém a interface pode exibir área admin até as chamadas falharem.

Impacto: UX confusa, falso positivo de login e possíveis erros em cascata.

Recomendação: no boot do admin, chamar `/api/auth/session/current` e só liberar UI se a sessão real retornar `role=admin`.

## 5. Riscos remanescentes priorizados

### P1 — `SESSION_SECRET` tem fallback inseguro

Severidade: alta se produção rodar sem variáveis corretas.

`SESSION_SECRET` usa, em ordem, `SESSION_SECRET`, `GOOGLE_CLIENT_SECRET`, `ASAAS_API_KEY` ou `"amigopet-dev-session-secret"`. Se produção subir sem segredo explícito e sem chaves de terceiros, sessões HMAC ficam assinadas com valor público.

Recomendação: em produção, falhar o startup se `SESSION_SECRET` não estiver definido com valor forte. Não usar segredo de gateway/OAuth como fallback de sessão.

### P2 — CORS permissivo com credenciais

Severidade: alta/média.

`allow_origins=os.getenv("CORS_ORIGINS", "*").split(",")` e `allow_credentials=True`. Mesmo que navegadores rejeitem `*` com credenciais em alguns cenários, a configuração é perigosa e tende a ser ajustada de forma insegura.

Recomendação: exigir `CORS_ORIGINS` explícito em produção, com domínios exatos, e negar wildcard com credenciais.

### P3 — Ausência de rate limiting e proteção anti-abuso

Severidade: alta.

Login, cadastro, reset de senha, Google callback, webhooks e criação de pedidos não têm limite por IP/conta. O reset usa código de 6 dígitos e não possui contador de tentativas.

Recomendação: implementar rate limit por IP/identidade, backoff, contador de tentativas em reset e lock temporário.

### P4 — Hash de senha usa SHA-256 simples

Severidade: alta em caso de vazamento de banco.

`hash_password()` usa `sha256(salt:password)` com salt, mas sem custo adaptativo. Isso é fraco para armazenamento de senhas.

Recomendação: migrar para Argon2id, bcrypt ou PBKDF2 com parâmetros adequados; suportar verificação de hashes antigos e rehash no login.

### P5 — CSRF em rotas autenticadas por cookie

Severidade: média/alta.

Sessão é cookie `HttpOnly`, `Secure`, `SameSite=Lax`. Isso ajuda, mas não substitui token CSRF para POST/PUT críticos, especialmente em fluxos de pagamento, perfil, passeio e wallet.

Recomendação: adicionar token CSRF para mutações ou usar padrão de sessão com cabeçalho custom validado.

### P6 — DTOs ainda amplos para participantes e admin

Severidade: média.

`walk_to_dict()` inclui PIX/QR code, ids de pagamento, status de repasse, erro de repasse, localização e valores. Agora só é retornado para admin/participantes, mas o ideal é separar respostas por contexto:

- cliente: pagamento próprio e status do passeio;
- passeador: dados operacionais necessários, sem QR PIX do cliente quando não necessário;
- admin: dados financeiros completos;
- evento WebSocket: payload mínimo do evento.

### P7 — WebSocket em memória não escala e perde eventos

Severidade: média.

`ConnectionManager` mantém conexões em memória no processo. Em múltiplas instâncias/workers, eventos enviados por uma instância não chegam a usuários conectados em outra.

Recomendação: Redis pub/sub, filas ou gerenciador externo; sticky sessions apenas como mitigação temporária.

### P8 — Webhook Asaas depende apenas de token estático e permite atualização de pedido por referência externa

Severidade: média.

O webhook valida `ASAAS_WEBHOOK_TOKEN`, o que é melhor que estar aberto. Ainda assim, é sensível: se o token vazar, eventos podem tentar atualizar pagamentos. O código também aceita objeto de pagamento do corpo se a consulta ao gateway falhar.

Recomendação: rejeitar eventos quando a consulta ao Asaas falhar para eventos de confirmação; validar valor, externalReference, payment id, status e customer; logar auditoria.

### P9 — Código legado duplicado com falhas antigas

Severidade: média de manutenção; alta se for implantado por engano.

Arquivos como `backend_patch/app/main.py`, `backend/app/main_backup_google.py` e módulos em `backend/app/api/*` contêm rotas/implementações antigas, algumas com senha `123456`, endpoints sem o mesmo hardening e padrões divergentes. O deploy atual usa `backend.app.main:app`, mas a presença desses arquivos aumenta risco de import/deploy errado.

Recomendação: mover legados para pasta fora do pacote importável ou remover após backup em git.

### P10 — Frontend com endpoints hardcoded de produção

Severidade: média.

`frontend/app.js` e `frontend/walker.js` usam `https://amigopet-6td8.onrender.com` e `wss://amigopet-6td8.onrender.com/ws`. Isso dificulta staging, testes locais e troca de domínio.

Recomendação: usar origem relativa (`location.origin`) ou configuração por build.

### P11 — Dependência de CDN sem SRI/CSP

Severidade: média.

Leaflet é carregado de `https://unpkg.com` sem Subresource Integrity e não há CSP. Se CDN ou cadeia for comprometida, o app recebe script de terceiros com acesso ao DOM.

Recomendação: versionar dependências localmente ou usar SRI + CSP restritiva.

### P12 — Uso extensivo de `innerHTML`

Severidade: média.

Há muitos pontos de renderização via `innerHTML`. Alguns usam `escapeHtml`, outros constroem HTML com dados vindos do backend. Isso eleva risco de XSS persistente caso algum campo salvo escape da sanitização.

Recomendação: padronizar renderização segura, revisar todos os templates e sanitizar/escapar na fronteira.

### P13 — Admin exposto em rota pública

Severidade: média/baixa.

`/admin` serve a UI publicamente. O backend protege APIs, mas a superfície de ataque e enumeração fica explícita.

Recomendação: proteger por autenticação desde o carregamento, restringir por IP/VPN ou ao menos remover e-mails pré-preenchidos e validar sessão real no boot.

### P14 — Banco e migrations improvisadas

Severidade: média.

`run_lightweight_migrations()` executa DDL manual no startup, com `safe()` que apenas imprime warning. Isso pode mascarar falhas de schema e deixar produção parcialmente migrada.

Recomendação: adotar Alembic, migrations versionadas e falha explícita quando migração crítica falhar.

### P15 — Testes automatizados praticamente inexistentes para segurança

Severidade: média.

Há `backend/tests.http`, mas ele referencia endpoints antigos (`/api/users/register`, `/api/health`) e não cobre autorização, propriedade, WebSocket, pagamentos, webhooks ou regressões de frontend.

Recomendação: criar testes pytest para matriz de autorização e Playwright/API tests para fluxos cliente/passeador/admin.

## 6. Observações por camada

### Backend ativo

Pontos fortes após correções:

- Dependências centralizadas de autenticação/papel.
- Participação validada em passeios, chat, avaliações, notificações e wallet.
- WebSocket autenticado e roteado por usuário.
- Admin pricing/payout protegido.
- Seeds desativados em produção detectada.

Pontos fracos:

- Monolito grande em um único arquivo com muita regra de negócio misturada.
- Sem testes de regressão de segurança.
- Sessão própria HMAC sem rotação, revogação individual ou store server-side.
- Sem política de senha forte.
- Sem rate limit.

### Frontend web

Pontos fortes:

- Fluxo Google web usa `/api/auth/session/current`, não ID em URL.
- API protegida no backend impede abuso mesmo quando UI guarda dados em `localStorage`.

Pontos fracos:

- Estado do usuário em `localStorage` pode ficar obsoleto/falso.
- Muitos `innerHTML`.
- Endpoints hardcoded.
- Chamadas a endpoints inexistentes.
- Cadastro de passeador por e-mail incompatível.

### Apps Android/WebView

Pontos fortes:

- `MixedContentMode` bloqueia conteúdo misto.
- HTTPS hardcoded para produção.

Pontos fracos:

- Login Google nativo depende de endpoints ausentes.
- WebView carrega qualquer URL `http://`/`https://` via `view.loadUrl(url)`, ampliando risco de navegação fora do domínio dentro do app.
- Permissões de localização/câmera/notificações são solicitadas em bloco.

### Operação/deploy

Pontos fortes:

- Render aponta para `backend.app.main:app`, o app corrigido.
- Dockerfile backend também aponta para `app.main:app` dentro do pacote backend copiado.

Pontos fracos:

- `docker-compose.yml` mapeia porta `8000:8000`, mas Dockerfile expõe/roda 10000; risco de ambiente local quebrado.
- `requirements.txt` raiz e `backend/requirements.txt` divergem.
- Documentação e `tests.http` estão desatualizados.

## 7. Recomendações de próxima etapa

Prioridade imediata:

1. Corrigir regressão do cadastro de passeador por e-mail ou remover/ocultar esse fluxo até existir candidatura aprovada.
2. Decidir estratégia do Google Android: OAuth web sem interceptação ou endpoints nativos seguros.
3. Exigir `SESSION_SECRET` forte em produção e restringir CORS.
4. Implementar rate limiting para auth/reset/webhooks/criação de pedidos.
5. Migrar hash de senha para Argon2id/bcrypt/PBKDF2.
6. Criar testes automatizados para C-01 a C-08, garantindo que não voltem.

Antes de produção:

1. Separar DTOs por contexto e evento.
2. Adotar Alembic.
3. Remover ou arquivar código legado duplicado.
4. Introduzir CSP/SRI e revisar `innerHTML`.
5. Trocar endpoints hardcoded por configuração.
6. Planejar WebSocket com Redis/pub-sub se houver múltiplas instâncias.

## 8. Conclusão

Os achados críticos C-01, C-02, C-03, C-04, C-05, C-06 e C-08 foram eliminados no backend ativo. O C-07 foi eliminado na exposição pública principal (`/api/users`) e mitigado por autorização nas demais rotas, mas ainda recomendo DTOs mínimos por contexto para reduzir vazamento entre participantes/admin e em eventos.

O risco atual mudou de “exploração trivial pública” para “hardening incompleto, regressões funcionais e dívida operacional”. A próxima rodada deve priorizar regressões de cadastro/login Android e controles transversais de produção: segredo obrigatório, CORS restrito, rate limit, hash de senha forte e testes de autorização.
