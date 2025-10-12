from datetime import datetime, timedelta

import requests
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model

from rest_framework import status
from acm.exceptions import CustomAPIException
from acm import error_codes as EC

from payment.models import Payment
from payment.services import initiate_payment_for_target
from .models import Course, Registration, RegistrationItem, _is_full_by_count
from notification.services import send_status_change_email
from accounts.models import UserExtraData
from django.conf import settings

User = get_user_model()

SKYROOM_BASEURL = settings.SKYROOM_BASEURL
SKYROOM_APIKEY = settings.SKYROOM_APIKEY
SKYROOM_ROOMID = settings.SKYROOM_ROOMID
HEADERS = {"accept": "application/json", "content-type": "application/json"}


def _is_full(capacity: int | None, taken: int) -> bool:
    if capacity is None:
        return False
    if capacity == 0:
        return True
    return taken >= capacity


def _parent_capacity_full(course: Course) -> bool:
    return _is_full_by_count(course)


def _child_capacity_full(child: Course) -> bool:
    return _is_full_by_count(child)


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
    Do NOT block when full.
    If parent OR any child is full => set RESERVED and force approval.
    Else QUEUED.
    If no approval required AND status is QUEUED => auto-approve/finalize (free) or create payment link.

    Additionally: prevent buying a course/child that the user already owns (FINAL),
    even if ownership came through a different parent registration.
    """
    if (not user.is_authenticated) or (not getattr(user, "is_email_verified", False)):
        raise CustomAPIException(
            code=EC.ACC_EMAIL_NOT_VERIFIED,
            message="Login with verified email required",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    child_ids = list(dict.fromkeys(child_ids or []))

    valid_children_qs = course.children.filter(is_active=True, id__in=child_ids)
    valid_children = list(valid_children_qs)
    if len(valid_children) != len(child_ids):
        raise CustomAPIException(
            code=EC.REG_CHILD_INVALID_SELECTION,
            message="One or more selected child presentations are invalid.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # ----------------------------
    # ALREADY-OWNED GUARD
    # ----------------------------
    # All finalized registrations for this user:
    finalized_regs = Registration.objects.filter(
        user=user,
        status=Registration.Status.FINAL,
    )

    owned_parent_ids = set(finalized_regs.values_list("course_id", flat=True))
    owned_child_ids = set(
        RegistrationItem.objects.filter(registration__in=finalized_regs)
        .values_list("child_course_id", flat=True)
    )
    owned_ids = owned_parent_ids | owned_child_ids

    if course.id in owned_ids:
        raise CustomAPIException(
            code=EC.REG_ALREADY_OWNED,
            message="You already own this presentation.",
            status_code=status.HTTP_409_CONFLICT,
        )

    already_owned_children = [c for c in valid_children if c.id in owned_ids]
    if already_owned_children:
        names = ", ".join(c.name for c in already_owned_children)
        raise CustomAPIException(
            code=EC.REG_CHILD_ALREADY_OWNED,
            message=f"You already own these selected child presentations: {names}",
            status_code=status.HTTP_409_CONFLICT,
        )

    parent_full = _parent_capacity_full(course)
    full_children = [c for c in valid_children if _child_capacity_full(c)]
    any_child_full = bool(full_children)
    forced_waitlist = parent_full or any_child_full

    reg, created = Registration.objects.get_or_create(course=course, user=user)
    if (not created) and reg.status in [Registration.Status.FINAL]:
        raise CustomAPIException(
            code=EC.REG_ALREADY_FINAL_OR_APPROVED,
            message="You already have an approved registration for this presentation.",
            status_code=status.HTTP_409_CONFLICT,
        )

    reg.resume_url = resume_url or reg.resume_url
    reg.submitted_at = timezone.now()
    reg.rejection_reason = ""
    reg.status = Registration.Status.RESERVED if forced_waitlist else Registration.Status.QUEUED
    reg.save()

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

    RegistrationItem.objects.filter(registration=reg).delete()
    for c in valid_children:
        RegistrationItem.objects.create(
            registration=reg,
            child_course=c,
            price=c.price,
        )

    send_status_change_email(
        to=user.email,
        status_code="COURSE_REQUEST_SUBMITTED",
        extra={
            "course": course.name,
            "status": reg.status,
            "waitlisted_children": ", ".join(ch.name for ch in full_children) if full_children else "",
        },
    )

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

        parent_id = reg.course.id
        child_ids = list(reg.items.values_list("child_course_id", flat=True))
        # target_id as a CSV bundle: "parent,child1,child2"
        bundle_target_id = ",".join([str(parent_id), *map(str, child_ids)])

        meta = {
            "reg_id": reg.id,
            "parent_course_id": parent_id,
            "child_course_ids": child_ids,
        }

        payment_result = initiate_payment_for_target(
            user=reg.user,
            target_type=Payment.TargetType.COURSE,
            target_id=bundle_target_id,
            amount=amount,
            description=description or _compose_description(reg),
            extra_metadata=meta,
        )
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
def set_status_final(regs: list[Registration], *, actor: User | None = None) -> list[Registration]:
    if len(regs) == 0:
        return regs

    for reg in regs:
        reg.status = Registration.Status.FINAL
        reg.decided_at = timezone.now()
        reg.save(update_fields=["status", "decided_at"])

    send_status_change_email(
        to=regs[0].user.email,
        status_code="COURSE_REQUEST_FINAL",
        extra={"course": regs[0].course.name},
    )
    return regs


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
    total = _compute_total_amount(reg)
    if total <= 0:
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


def _user_has_access_to_course(user, course) -> bool:
    return (
        # direct child registration
        Registration.objects.filter(
            user=user,
            status=Registration.Status.FINAL,
            course=course,
        ).exists()
        or
        # selected as a child item under a finalized parent registration
        Registration.objects.filter(
            user=user,
            status=Registration.Status.FINAL,
            items__child_course=course,
        ).exists()
        or
        # finalized to a parent (access to all children)
        Registration.objects.filter(
            user=user,
            status=Registration.Status.FINAL,
            course__children=course,
        ).exists()
    )

def _now_in_shift_window(course, *, window_minutes: int = 15, now: datetime | None = None) -> bool:
    if now is None:
        now = timezone.localtime()

    today_weekday = now.weekday()  # Monday=0
    rules = course.schedule.filter(weekday=today_weekday)

    if not rules.exists():
        return False

    # build datetimes for today using the course's schedule times
    for rule in rules:
        start_dt = timezone.make_aware(datetime.combine(now.date(), rule.start_time), now.tzinfo)
        end_dt   = timezone.make_aware(datetime.combine(now.date(), rule.end_time),   now.tzinfo)

        window_start = start_dt - timedelta(minutes=window_minutes)
        window_end   = end_dt + timedelta(minutes=window_minutes)

        if window_start <= now <= window_end:
            return True

    return False

# ---- your original functions, adapted ----

def create_skyroom_link(user: User, course: Course) -> str | None:
    """
    Returns the Skyroom login URL if the user is authorized AND within the shift window.
    Otherwise returns None (caller can decide to 400).
    """
    # 1) access check via parent/child relationships
    if not _user_has_access_to_course(user, course):
        return None

    # 2) timing check against today's shift
    if not _now_in_shift_window(course, window_minutes=15):
        return None

    # 3) generate link
    return get_skyroom_presentation_link(
        room_id=SKYROOM_ROOMID,
        user_id=user.email,
        nickname=f"{user.first_name} {user.last_name}",
    )

def get_skyroom_presentation_link(
        room_id: int = 1,
        user_id: str = "sina",
        nickname: str = "Sina",
        language: str = "fa",
        ttl: int = 5400):
    url = f"{SKYROOM_BASEURL}/skyroom/api/{SKYROOM_APIKEY}"
    payload = {
        "action": "createLoginUrl",
        "params": {
            "room_id": room_id,
            "user_id": user_id,
            "nickname": nickname,
            "access": 1,      # Access level
            "concurrent": 1,
            "language": language,
            "ttl": ttl,
        },
    }
    r = requests.post(url, json=payload, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.json().get("result", None)