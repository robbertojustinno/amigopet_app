# Manual de Deploy Profissional - AmigoPet V8 REAL

## 1. O que subir
Você vai subir a pasta do projeto inteira.

## 2. Variáveis de ambiente mínimas
Defina estas variáveis no Render:

- `SECRET_KEY`
- `DATABASE_URL`
- `REDIS_URL`
- `DEFAULT_ADDRESS`
- `MERCADO_PAGO_ACCESS_TOKEN`
- `MERCADO_PAGO_PUBLIC_KEY`

## 3. Banco em produção
Use PostgreSQL.
Exemplo:
```env
DATABASE_URL=postgresql+psycopg2://usuario:senha@host:5432/banco
```

## 4. Redis
Crie uma instância Redis no provedor escolhido e copie a URL:
```env
REDIS_URL=redis://usuario:senha@host:6379/0
```

## 5. Build
No backend, o Dockerfile já está pronto.

## 6. Domínio
Depois do deploy, configure:
- domínio personalizado
- HTTPS automático
- variáveis secretas

## 7. Pagamento real Mercado Pago
No painel do Mercado Pago:
- gere `ACCESS TOKEN`
- gere `PUBLIC KEY`
- cole no painel do Render

## 8. Arquivos de imagem
No ambiente atual, as fotos ficam em `backend/storage`.
Para produção de alto nível, troque por:
- Cloudinary
- S3
- Supabase Storage

## 9. Próximas melhorias recomendadas
- login com JWT refresh token
- WebSocket em produção
- push notifications com Firebase
- tracking GPS em tempo real
- painel admin
- antifraude de pagamento

## 10. Subida rápida local
```bash
cp .env.example .env
docker compose up --build
```
