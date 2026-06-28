AmigoPet Patch 007 - Carteira Financeira do Passeador

Arquivos alterados:
- backend/app/main.py
- frontend/passeador.html
- frontend/walker.js
- frontend/styles.css

O que foi implementado:
- Nova aba Carteira no app do passeador.
- Resumo financeiro com saldo disponível, saldo pendente, total bruto e passeios finalizados.
- Histórico financeiro por passeio finalizado.
- Endpoints:
  GET /api/wallet/{walker_id}
  GET /api/wallet/{walker_id}/history
- Cálculo usando os dados reais de walk_requests: estimated_price, payout_amount, payout_status e comissão configurada.
- Preparado para repasse PIX/Asaas e dashboard financeiro futuro.

Comandos Git:
cd E:\amigopet_app

git status

git add backend/app/main.py frontend/passeador.html frontend/walker.js frontend/styles.css

git commit -m "Patch 007 - Carteira Financeira do Passeador"

git push origin main

Teste recomendado:
1. Aguardar deploy no Render.
2. Abrir /passeador.
3. Fazer login Google como passeador.
4. Verificar a nova aba Carteira.
5. Finalizar um passeio de teste e atualizar a carteira.
