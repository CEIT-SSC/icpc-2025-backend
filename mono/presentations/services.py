from django.db import transaction
from django.utils import timezone
from django.core.exceptions import PermissionDenied, ValidationError
from django.contrib.auth import get_user_model
from .models import Course, Registration
from notification.services import send_status_change_email
from accounts.models import UserExtraData

User = get_user_model()

# Helpers

def _capacity_full(course: Course) -> bool:
    # Count approved + final? Spec says queue vs reserve on submission time.
    # We'll consider APPROVED and FINAL as taking a seat; QUEUED/RESERVED do not.
    taken = course.registrations.filter(status__in=[Registration.Status.APPROVED, Registration.Status.FINAL]).count()
    return course.capacity > 0 and taken >= course.capacity

# Public API

@transaction.atomic
def submit_registration(*, course: Course, user: User, resume_url: str | None, extra_updates: dict | None) -> Registration:
    if not user.is_authenticated or not getattr(user, "is_email_verified", False):
        raise PermissionDenied("Login with verified email required")

    reg, created = Registration.objects.get_or_create(course=course, user=user)
    if not created and reg.status in [Registration.Status.APPROVED, Registration.Status.FINAL]:
        raise ValidationError("Already approved/final")

    reg.resume_url = resume_url or reg.resume_url
    reg.status = Registration.Status.RESERVED if _capacity_full(course) else Registration.Status.QUEUED
    reg.submitted_at = timezone.now()
    reg.rejection_reason = ""
    reg.save()

    # Update user's extra data
    if extra_updates:
        extra, _ = UserExtraData.objects.get_or_create(user=user)
        # Merge shallowly
        extra.answers = {**(extra.answers or {}), **extra_updates}
        # Map well-known fields if present
        if "codeforces_score" in extra_updates:
            try:
                extra.codeforces_score = int(extra_updates["codeforces_score"])
            except Exception:
                pass
        if "codeforces_handle" in extra_updates:
            extra.codeforces_handle = str(extra_updates["codeforces_handle"])[:64]
        extra.save()

    # Email user about submission
    send_status_change_email(
        to=user.email,
        status_code="COURSE_REQUEST_SUBMITTED",
        extra={"course": course.name, "status": reg.status},
    )
    return reg

@transaction.atomic
def set_status_approved(reg: Registration, *, actor: User | None = None, payment_link: str | None = None) -> Registration:
    reg.status = Registration.Status.APPROVED
    reg.payment_link = payment_link or reg.payment_link
    reg.decided_at = timezone.now()
    reg.save(update_fields=["status", "payment_link", "decided_at"])
    send_status_change_email(
        to=reg.user.email,
        status_code="COURSE_REQUEST_APPROVED",
        extra={"course": reg.course.name, "payment_link": reg.payment_link},
    )
    return reg

@transaction.atomic
def set_status_final(reg: Registration, *, actor: User | None = None) -> Registration:
    reg.status = Registration.Status.FINAL
    reg.decided_at = timezone.now()
    reg.save(update_fields=["status", "decided_at"])
    send_status_change_email(
        to=reg.user.email,
        status_code="COURSE_REQUEST_FINAL",
        extra={"course": reg.course.name},
    )
    return reg

@transaction.atomic
def set_status_rejected(reg: Registration, *, actor: User | None = None) -> Registration:
    if not reg.rejection_reason:
        raise ValidationError("rejection_reason must be set before rejecting")
    reg.status = Registration.Status.REJECTED
    reg.decided_at = timezone.now()
    reg.save(update_fields=["status", "decided_at"])
    send_status_change_email(
        to=reg.user.email,
        status_code="COURSE_REQUEST_REJECTED",
        extra={"course": reg.course.name, "reason": reg.rejection_reason},
    )
    return reg