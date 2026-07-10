# Pagamentos AmigoPet

O AmigoPet usa Asaas para cobranças de passeios.

## Formas Disponíveis

- PIX
- Cartão de crédito

O PIX continua sendo a opção padrão.

## Fluxo Do Cliente

1. Cliente logado escolhe pet, passeador, duração e quantidade de cães.
2. Cliente escolhe a forma de pagamento:
   - `PIX`
   - `Cartão de crédito`
3. Ao enviar o convite, o backend cria o passeio.
4. O backend tenta criar a cobrança Asaas.
5. O passeador só pode aceitar depois que `payment_status` estiver `pago`.

## PIX

Para PIX, o backend cria cobrança Asaas com:

```json
{
  "billingType": "PIX"
}
```

Quando o Asaas retorna QR Code, o backend salva:

- código copia-e-cola PIX;
- imagem base64 do QR Code, quando disponível;
- URL do pagamento, quando disponível;
- ID da cobrança Asaas.

## Cartão De Crédito

Para cartão, o backend cria cobrança Asaas com:

```json
{
  "billingType": "CREDIT_CARD"
}
```

O frontend envia os dados do cartão apenas no momento da cobrança.

Dados enviados ao backend:

- nome impresso no cartão;
- número do cartão;
- mês e ano de vencimento;
- CVV;
- CPF/CNPJ do titular;
- CEP do titular;
- número do endereço do titular;
- telefone do titular.

## Segurança Dos Dados Do Cartão

O AmigoPet não salva no banco:

- número do cartão;
- CVV;
- vencimento;
- dados completos do cartão.

O banco salva apenas:

- método de pagamento escolhido (`PIX` ou `CREDIT_CARD`);
- ID da cobrança Asaas;
- status retornado pelo Asaas;
- mensagens públicas sanitizadas em caso de falha.

## Webhook

O webhook Asaas aceita eventos de pagamento para PIX e cartão.

Quando o Asaas retorna status pago, como `RECEIVED` ou `CONFIRMED`, o backend:

- marca `payment_status` como `pago`;
- move o passeio para `pagamento_confirmado` quando aplicável;
- libera o aceite pelo passeador;
- envia evento em tempo real para cliente/passeador.

## Variáveis Necessárias

```env
ASAAS_API_KEY=...
ASAAS_WEBHOOK_TOKEN=...
ASAAS_ENV=production
ASAAS_BASE_URL=https://api.asaas.com/v3
PUBLIC_BASE_URL=https://seu-servico.onrender.com
```

## Observações Operacionais

- Em sandbox, use as credenciais e cartões de teste indicados pelo Asaas.
- Em produção, valide no painel Asaas se a conta está habilitada para cobrança por cartão.
- Se o cartão for recusado, o passeio pode ser criado, mas o pagamento continuará aguardando ou com erro de cobrança.
- O passeador não consegue aceitar passeio sem pagamento confirmado.
