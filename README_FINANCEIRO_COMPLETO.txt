AMIGOPET - FINANCEIRO COMPLETO

Substitua estes arquivos no projeto:
- backend/app/api/routes.py
- backend/app/main.py
- backend/requirements.txt
- backend/Dockerfile
- render.yaml
- frontend/index.html
- frontend/styles.css
- frontend/app.js

Fluxo financeiro:
1. Passeador finaliza o passeio.
2. Cliente gera/paga PIX.
3. Webhook/status confirma pagamento.
4. Sistema calcula automaticamente:
   - preço bruto
   - comissão AmigoPet: 20%
   - saldo líquido do passeador: 80%
5. Sistema cria crédito na carteira do passeador.
6. Admin vê financeiro e pode marcar repasse como pago ou bloquear saldo.

Comandos:
git add .
git commit -m "activate full financial flow"
git push

Render:
Manual Deploy > Clear build cache & deploy
