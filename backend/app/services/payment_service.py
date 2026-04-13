from app.core.config import settings

class PaymentService:
    def __init__(self):
        self.access_token = settings.MERCADO_PAGO_ACCESS_TOKEN

    def create_fake_checkout(self, request_id: int, amount: float) -> dict:
        # Base pronta: aqui você pode substituir pela chamada real do Mercado Pago.
        return {
            "provider": "mercado_pago",
            "request_id": request_id,
            "amount": amount,
            "checkout_url": f"https://pagamento.exemplo.local/checkout/{request_id}",
            "status": "created" if self.access_token else "sandbox_pending_credentials"
        }

payment_service = PaymentService()
