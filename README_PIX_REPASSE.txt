AmigoPet - PIX do Passeador + Solicitação de Saque

Inclui:
- campos PIX no usuário passeador por migração automática;
- endpoint para salvar chave PIX do passeador;
- endpoint para solicitar saque com saldo disponível;
- admin visualiza PIX na transação de saque;
- admin marca saque como repassado/pago;
- carteira calcula disponível líquido descontando saques solicitados.

Fluxo:
1. Cliente paga.
2. Sistema separa comissão admin e saldo do passeador.
3. Passeador cadastra chave PIX.
4. Passeador solicita saque.
5. Admin faz PIX manualmente e marca como repassado.

Após substituir:
git add .
git commit -m "add walker pix withdraw flow"
git push

Render:
Manual Deploy > Clear build cache & deploy
