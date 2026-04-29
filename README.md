# AmigoPet Pro

Plataforma profissional inicial para passeio de pets: cliente, passeador e admin no mesmo frontend, com backend FastAPI e SQLite.

## Rodar no Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn backend.app.main:app --reload
```

Abra:

http://127.0.0.1:8000

## Login rápido

O sistema cria dados iniciais automaticamente:

- Admin: admin@amigopet.com / 123456
- Cliente: cliente@amigopet.com / 123456
- Passeador: passeador@amigopet.com / 123456

## Deploy Render

Build Command:

```bash
pip install -r requirements.txt
```

Start Command:

```bash
uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT
```
