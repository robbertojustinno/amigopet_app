# AmigoPet V8 REAL

Plataforma web estilo marketplace/Uber para passeadores de cachorro, com:

- cadastro de cliente e passeador
- foto obrigatória do passeador
- busca por bairro/cidade
- convite para passeador com contagem regressiva
- aceite/recusa com tempo limite
- chat interno no app
- pagamento com Mercado Pago (base pronta para integração real)
- mapa automático via OpenStreetMap
- deploy profissional com Docker e Render

## Stack

- **Backend:** FastAPI + SQLAlchemy + Pydantic
- **Frontend:** HTML + CSS + JavaScript puro
- **Banco:** SQLite local / PostgreSQL em produção
- **Fila/tempo real:** Redis (pub/sub e cache)
- **Deploy:** Docker / Render

## Estrutura

```bash
amigopet-v8-real/
├─ backend/
├─ frontend/
├─ docker-compose.yml
├─ .env.example
├─ render.yaml
└─ MANUAL_DEPLOY.md
```

## O que já está pronto

### Funcional real implementada
- API REST
- persistência de usuários, pets, solicitações e mensagens
- validação de foto obrigatória do passeador
- endereço padrão:
  **Rua Mirabel, 49 Piabetá - Magé - RJ CEP 25931-854**
- geração automática do mapa quando o endereço é digitado
- fluxo de solicitação com status:
  `pending -> invited -> accepted / declined / expired / paid / completed`
- cron de expiração de convite
- chat por solicitação
- frontend navegável e editável

### Pontos que exigem chave externa
- Mercado Pago real
- serviço de push notification real
- storage de imagens em nuvem (opcional em produção)

## Rodando localmente

### 1) copiar variáveis
```bash
cp .env.example .env
```

### 2) subir com Docker
```bash
docker compose up --build
```

### 3) acessar
- Frontend: http://localhost:8080
- API docs: http://localhost:8000/docs

## Login de demonstração
Crie contas pelo próprio frontend.

## Observação importante
Este pacote está **pronto como base profissional real**, mas integrações externas como pagamento e push dependem das suas credenciais.
