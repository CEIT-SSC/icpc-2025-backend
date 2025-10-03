from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model

from rest_framework import status
from acm.exceptions import CustomAPIException
from acm import error_codes as EC

from payment.models import Payment
from payment.services import initiate_payment_for_target
from .models import Course, Registration, RegistrationItem
from notification.services import send_status_change_email
from accounts.models import UserExtraData

User = get_user_model()


def _is_full(capacity: int | None, taken: int) -> bool:
    """
    Capacity rules:
      - None => unlimited (never full)
      - 0    => closed (always full)
      - >0   => full when taken >= capacity
    """
    if capacity is None:
        return False
    if capacity == 0:
        return True
    return taken >= capacity


def _parent_capacity_full(course: Course) -> bool:
    taken = course.registrations.filter(
        status__in=[Registration.Status.APPROVED, Registration.Status.FINAL]
    ).count()
    return _is_full(getattr(course, "capacity", None), taken)


def _child_capacity_full(child: Course) -> bool:
    """
    A child seat is taken when a Registration that includes this child is
    APPROVED or FINAL.
    """
    taken = RegistrationItem.objects.filter(
        child_course=child,
        registration__status__in=[Registration.Status.APPROVED, Registration.Status.FINAL],
    ).count()
    return _is_full(getattr(child, "capacity", None), taken)


def _compute_total_amount(reg: Registration) -> int:
    parent = reg.course.price or 0
    children = sum((i.price or 0) for i in reg.items.all())
    return parent + children


def _compose_description(reg: Registration) -> str:
    child_slugs = ", ".join(i.child_course.slug for i in reg.items.all())
    if child_slugs:
        return f"{reg.course.slug} + [{child_slugs}]"
    return reg.course.slug


@transaction.atomic
def submit_registration(
    *,
    course: Course,
    user: User,
    extra_updates: dict | None = None,
    child_ids: list[int] | None = None,
    resume_url: str | None = None,
) -> Registration:
    """
    Create/replace a user's registration for a parent course with selected children.

    Behavior:
      - Do NOT block when full.
      - If parent OR any child is full => set RESERVED and force approval (even if requires_approval=False).
      - Else QUEUED.
      - If no approval required AND status is QUEUED => auto-approve/finalize (free) or create payment link.
    """
    if (not user.is_authenticated) or (not getattr(user, "is_email_verified", False)):
        raise CustomAPIException(
            code=EC.ACC_EMAIL_NOT_VERIFIED,
            message="Login with verified email required",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    child_ids = child_ids or []

    # Validate selected children are active and actually belong to this course
    valid_children_qs = course.children.filter(is_active=True, id__in=child_ids)
    valid_children = list(valid_children_qs)
    if len(valid_children) != len(child_ids):
        raise CustomAPIException(
            code=EC.REG_CHILD_INVALID_SELECTION,
            message="One or more selected child presentations are invalid.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # Capacity snapshot
    parent_full = _parent_capacity_full(course)
    full_children = [c for c in valid_children if _child_capacity_full(c)]
    any_child_full = bool(full_children)
    forced_waitlist = parent_full or any_child_full  # => RESERVED + approval flow

    # Create or reuse the registration
    reg, created = Registration.objects.get_or_create(course=course, user=user)
    if (not created) and reg.status in [Registration.Status.APPROVED, Registration.Status.FINAL]:
        raise CustomAPIException(
            code=EC.REG_ALREADY_FINAL_OR_APPROVED,
            message="You already have an approved/final registration for this presentation.",
            status_code=status.HTTP_409_CONFLICT,
        )

    # Update main fields
    reg.resume_url = resume_url or reg.resume_url
    reg.submitted_at = timezone.now()
    reg.rejection_reason = ""

    # Initial status
    reg.status = Registration.Status.RESERVED if forced_waitlist else Registration.Status.QUEUED
    reg.save()

    # Save extra applicant data (best-effort)
    if extra_updates:
        extra, _ = UserExtraData.objects.get_or_create(user=user)
        extra.answers = {**(extra.answers or {}), **extra_updates}
        if "codeforces_score" in extra_updates:
            try:
                extra.codeforces_score = int(extra_updates["codeforces_score"])
            except Exception:
                pass
        if "codeforces_handle" in extra_updates:
            extra.codeforces_handle = str(extra_updates["codeforces_handle"])[:64]
        extra.save()

    # Refresh children selections
    RegistrationItem.objects.filter(registration=reg).delete()
    for c in valid_children:
        RegistrationItem.objects.create(
            registration=reg,
            child_course=c,
            price=c.price,
        )

    # Notify submit
    send_status_change_email(
        to=user.email,
        status_code="COURSE_REQUEST_SUBMITTED",
        extra={
            "course": course.name,
            "status": reg.status,
            "waitlisted_children": ", ".join(ch.name for ch in full_children) if full_children else "",
        },
    )

    # If any capacity is full, or course/child requires approval, do NOT auto-progress.
    requires_approval = bool(getattr(course, "requires_approval", False)) or any(
        getattr(c, "requires_approval", False) for c in valid_children
    ) or forced_waitlist

    if not requires_approval and reg.status == Registration.Status.QUEUED:
        _auto_progress_to_payment(reg)

    return reg


@transaction.atomic
def set_status_approved(
    reg: Registration,
    *,
    actor: User | None = None,
    payment_link: str | None = None,
    override_amount: int | None = None,
    description: str | None = None,
) -> Registration:
    reg.status = Registration.Status.APPROVED

    if payment_link is None:
        amount = override_amount if override_amount is not None else _compute_total_amount(reg)
        try:
            payment_result = initiate_payment_for_target(
                user=reg.user,
                target_type=Payment.TargetType.COURSE,  # keep existing target type
                target_id=reg.course.id,
                amount=amount,
                description=description or _compose_description(reg),
            )
        except CustomAPIException:
            # Bubble up payment-layer codes (e.g., PAY_INIT_FAILED / PAY_GATEWAY_REFUSED)
            raise
        reg.payment_link = payment_result.url
    else:
        reg.payment_link = payment_link

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
        raise CustomAPIException(
            code=EC.REG_REJECTION_REASON_REQUIRED,
            message="rejection_reason must be set before rejecting",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    reg.status = Registration.Status.REJECTED
    reg.decided_at = timezone.now()
    reg.save(update_fields=["status", "decided_at"])
    send_status_change_email(
        to=reg.user.email,
        status_code="COURSE_REQUEST_REJECTED",
        extra={"course": reg.course.name, "reason": reg.rejection_reason},
    )
    return reg


def _auto_progress_to_payment(reg: Registration) -> None:
    """
    Auto-approve or auto-finalize (if free) when approval is NOT required and status is QUEUED.
    """
    total = _compute_total_amount(reg)
    if total <= 0:
        # Free registration — finalize directly
        reg.status = Registration.Status.FINAL
        reg.decided_at = timezone.now()
        reg.payment_link = ""
        reg.save(update_fields=["status", "decided_at", "payment_link"])
        send_status_change_email(
            to=reg.user.email,
            status_code="COURSE_REQUEST_FINAL",
            extra={"course": reg.course.name},
        )
    else:
        set_status_approved(reg, override_amount=total, description=_compose_description(reg))
