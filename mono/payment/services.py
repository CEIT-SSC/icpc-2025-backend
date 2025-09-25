# payment/services.py

import requests
from dataclasses import dataclass
from typing import Optional, List, Dict
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError, PermissionDenied
from django.contrib.auth import get_user_model

from .models import Payment
from .domain_hooks import on_payment_success, on_payment_failure

User = get_user_model()

# ---- Zarinpal endpoints ----
Z_BASE = "https://payment.zarinpal.com/pg/v4/payment"
HEADERS = {"accept": "application/json", "content-type": "application/json"}


@dataclass
class StartPayResult:
    url: str
    payment: Payment


# ---- Helpers ----
def _callback_url() -> str:
    """
    Backend callback URL that Zarinpal will redirect the user to.
    This endpoint should redirect to the frontend (PAYMENT_FRONTEND_RETURN) with ?authority=...
    """
    return settings.PAYMENT_CALLBACK_BASE


def _unverified_list() -> List[Dict]:
    """
    Fetches the list of unverified authorities from Zarinpal.
    Returns [] on non-100 or network error.
    """
    url = f"{Z_BASE}/unVerified.json"
    try:
        r = requests.get(url, headers={"accept": "application/json"}, timeout=15)
        r.raise_for_status()
        data = r.json().get("data", {})
        if str(data.get("code")) != "100":
            return []
        return data.get("authorities", []) or []
    except requests.RequestException:
        return []


def _request_payment(
        *, merchant_id: str, amount: int, description: str, email: str, mobile: Optional[str] = None
) -> dict:
    url = f"{Z_BASE}/request.json"
    payload = {
        "merchant_id": merchant_id,
        "amount": amount,
        "callback_url": _callback_url(),
        "description": description or "ACM purchase",
        "metadata": {"email": email, **({"mobile": mobile} if mobile else {})},
    }
    r = requests.post(url, json=payload, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.json()


def _verify_payment(*, merchant_id: str, amount: int, authority: str) -> dict:
    url = f"{Z_BASE}/verify.json"
    payload = {"merchant_id": merchant_id, "amount": amount, "authority": authority}
    r = requests.post(url, json=payload, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.json()


# ---- Public API ----
@transaction.atomic
def initiate_payment_for_target(
        *,
        user: User,
        target_type: str,
        target_id: int,
        amount: int,
        currency: str = "IRR",
        description: str = "",
) -> StartPayResult:
    """
    1) Check existing PENDING payments for the user; if any authority is still unverified at the gateway,
       attempt to verify it. If verification succeeds for SAME target, raise conflict.
    2) Create a new Zarinpal request and persist a PENDING Payment with the returned authority.
    3) Return StartPay URL.
    """
    if not user or not user.is_authenticated:
        raise PermissionDenied("Authentication required")

    merchant = settings.ZARINPAL_MERCHANT_ID
    if not merchant:
        raise ValidationError("Payment merchant id not configured")

    # Step 1: verify any outstanding PENDING payments present in unVerified list
    pending = list(Payment.objects.select_for_update().filter(user=user, status=Payment.Status.PENDING))
    if pending:
        authorities_map = {item.get("authority"): item for item in _unverified_list()}
        for p in pending:
            if p.authority and p.authority in authorities_map:
                v = _verify_payment(merchant_id=merchant, amount=p.amount, authority=p.authority)
                d = v.get("data", {})
                code = d.get("code")
                p.zarinpal_code = str(code)
                p.zarinpal_message = d.get("message", "")
                if code == 100:
                    p.status = Payment.Status.SUCCESSFUL
                    p.ref_id = str(d.get("ref_id", ""))
                    p.card_pan = str(d.get("card_pan", ""))
                    p.card_hash = str(d.get("card_hash", ""))
                    p.save()
                    # conflict if same purchase already paid
                    if p.target_type == target_type and p.target_id == target_id:
                        raise ValidationError({"detail": "Conflict: existing successful payment found for this purchase"})
                else:
                    p.status = Payment.Status.FAILED
                    p.save()

    # Step 2: request payment
    try:
        res = _request_payment(
            merchant_id=merchant,
            amount=amount,
            description=description or f"{target_type}:{target_id}",
            email=user.email,
            mobile=getattr(user, "phone_number", None),
        )
    except requests.RequestException as e:
        Payment.objects.create(
            user=user,
            target_type=target_type,
            target_id=target_id,
            amount=amount,
            currency=currency,
            status=Payment.Status.PG_INITIATE_ERROR,
            zarinpal_message=str(e),
            description=description or "",
            metadata={"stage": "request", "exc": str(e)},
        )
        raise ValidationError({"detail": "Payment gateway error while initiating"})

    d = res.get("data", {}) or {}
    code = d.get("code")
    if code != 100:
        Payment.objects.create(
            user=user,
            target_type=target_type,
            target_id=target_id,
            amount=amount,
            currency=currency,
            status=Payment.Status.PG_INITIATE_ERROR,
            zarinpal_code=str(code),
            zarinpal_message=d.get("message", ""),
            description=description or "",
            metadata={"stage": "request", "resp": d},
        )
        raise ValidationError({"detail": f"Gateway refused: {d.get('message', '')}"})

    authority = d.get("authority")
    pay = Payment.objects.create(
        user=user,
        target_type=target_type,
        target_id=target_id,
        amount=amount,
        currency=currency,
        status=Payment.Status.PENDING,
        authority=authority,
        description=description or "",
        metadata={"fee_type": d.get("fee_type"), "fee": d.get("fee")},
    )
    startpay_url = f"https://payment.zarinpal.com/pg/StartPay/{authority}"
    return StartPayResult(url=startpay_url, payment=pay)


@transaction.atomic
def verify_by_authority(*, user: User, authority: str) -> Payment:
    """
    Verify a payment by authority for the given user (frontend passes authority after redirect).
    On success/failure, updates Payment and triggers domain hooks.
    """
    if not user or not user.is_authenticated:
        raise PermissionDenied("Authentication required")

    try:
        p = Payment.objects.select_for_update().get(user=user, authority=authority)
    except Payment.DoesNotExist:
        raise ValidationError("Payment not found for this user/authority")

    if p.status != Payment.Status.PENDING:
        # Already processed; no-op
        return p

    merchant = settings.ZARINPAL_MERCHANT_ID
    try:
        res = _verify_payment(merchant_id=merchant, amount=p.amount, authority=authority)
    except requests.RequestException as e:
        p.status = Payment.Status.FAILED
        p.zarinpal_message = str(e)
        p.save(update_fields=["status", "zarinpal_message"])
        on_payment_failure(p)
        return p

    d = res.get("data", {}) or {}
    code = d.get("code")
    p.zarinpal_code = str(code)
    p.zarinpal_message = d.get("message", "")

    if code == 100:
        p.status = Payment.Status.SUCCESSFUL
        p.ref_id = str(d.get("ref_id", ""))
        p.card_pan = str(d.get("card_pan", ""))
        p.card_hash = str(d.get("card_hash", ""))
        p.save()
        on_payment_success(p)
    else:
        p.status = Payment.Status.FAILED
        p.save()
        on_payment_failure(p)

    return p
