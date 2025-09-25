# payment/domain_hooks.py
from .models import Payment

def on_payment_success(payment: Payment):
    if payment.target_type == Payment.TargetType.COMPETITION:
        from competitions.models import TeamRequest
        from competitions.services import mark_payment_final
        tr = TeamRequest.objects.get(id=payment.target_id)
        mark_payment_final(tr)
    elif payment.target_type == Payment.TargetType.COURSE:
        from presentations.models import Registration
        from presentations.services import set_status_final
        reg = Registration.objects.get(id=payment.target_id)
        set_status_final(reg)

def on_payment_failure(payment: Payment):
    if payment.target_type == Payment.TargetType.COMPETITION:
        from competitions.models import TeamRequest
        from competitions.services import mark_payment_rejected
        tr = TeamRequest.objects.get(id=payment.target_id)
        mark_payment_rejected(tr)
