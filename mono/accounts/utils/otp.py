import hmac, secrets, string
from hashlib import sha256
from dataclasses import dataclass
from django.conf import settings
from django.core.cache import cache

OTP_TTL = 5 * 60  # 5 minutes
RESEND_WINDOW_SEC = 30
MAX_PER_HOUR = 3

@dataclass
class OtpRecord:
    email: str
    intent: str
    user_id: int | None

# helpers

def _key(token: str) -> str:
    return f"otp:{token}"

def _rate_key(email: str) -> str:
    return f"otp:rate:{email}"

def generate_code(length: int = 6) -> str:
    alphabet = string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))

def hash_code(code: str) -> str:
    return hmac.new(settings.OTP_SECRET.encode(), code.encode(), sha256).hexdigest()

def create_otp(email: str, intent: str, user_id: int | None) -> tuple[str, str]:
    # rate limiting
    bucket = _rate_key(email)
    current = cache.get(bucket, 0)
    if current and int(current) >= MAX_PER_HOUR:
        raise ValueError("Too many OTP requests")
    cache.incr(bucket) if current else cache.set(bucket, 1, timeout=MAX_PER_HOUR)

    code = generate_code()
    token = secrets.token_urlsafe(24)
    data = {
        "hash": hash_code(code),
        "email": email,
        "intent": intent,
        "user_id": user_id,
    }
    cache.set(_key(token), data, timeout=OTP_TTL)
    return token, code

def verify_otp(token: str, code: str) -> OtpRecord | None:
    data = cache.get(_key(token))
    if not data:
        return None
    ok = hmac.compare_digest(data["hash"], hash_code(code))
    if not ok:
        return None
    cache.delete(_key(token))
    return OtpRecord(email=data["email"], intent=data["intent"], user_id=data["user_id"])