from .services import initiate_payment_for_target

def create_payment_link(*, competition_id: int | None = None, request_id: int | None = None, amount: str, currency: str = "IRR") -> str:
    """Compatibility shim for competitions app.
    Returns StartPay URL string. Assumes current authenticated user is the submitter in the view's request context; here we only wrap service.
    """
    raise NotImplementedError("Use payment.services.initiate_payment_for_target from an authenticated view context")    