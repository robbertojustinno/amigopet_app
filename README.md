# AmigoPet V6 nível Uber

Plataforma FastAPI + HTML/CSS/JS com fluxo estilo Uber para passeios com pets.

## Recursos
- Login cliente, passeador e admin
- Cadastro de pet
- Escolha do passeador antes da solicitação
- Convite com contador
- Aceitar/recusar pedido
- PIX simulado
- Chat interno
- Rastreamento visual simulado
- WebSocket para atualizações em tempo real
- Painel admin

## Rodar local
```powershell
cd E:\amigopet_app
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn backend.app.main:app --reload
```

Abra: http://127.0.0.1:8000

## Logins
- admin@amigopet.com / 123456
- cliente@amigopet.com / 123456
- passeador@amigopet.com / 123456
- ana@amigopet.com / 123456

## Render start command
```bash
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT
```
