# Deploy simples no Render

Este pacote foi ajustado para subir como **um único Web Service Docker** no Render.

## Como criar no Render
- New +
- Web Service
- Selecione o repositório
- Environment: Docker

## Campos
- Name: `amigopet-v8`
- Branch: `main`
- Dockerfile Path: `backend/Dockerfile`
- Docker Context: `.`

## Variáveis de ambiente mínimas
- `ENV=production`
- `SECRET_KEY=sua-chave-forte`
- `DATABASE_URL=sqlite:///./amigopet.db`
- `DEFAULT_ADDRESS=Rua Mirabel, 49 Piabetá - Magé - RJ CEP 25931-854`

## Observações
- O frontend agora é servido pelo próprio backend.
- O frontend chama a API em `/api` no mesmo domínio.
- Se quiser Redis depois, adicione `REDIS_URL`.
- Se quiser Mercado Pago real depois, adicione as chaves.
