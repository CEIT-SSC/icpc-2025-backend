import secrets, hmac
from hashlib import sha256
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model

from acm.exceptions import CustomAPIException
from acm import error_codes as EC

from .models import Competition, CompetitionFieldConfig, TeamRequest, TeamMember, FieldRequirement
from notification.services import send_status_change_email

User = get_user_model()

APPROVAL_TOKEN_TTL_MIN = 60 * 24
BLOCKING_STATUSES = {
    TeamRequest.Status.PENDING_APPROVAL,
    TeamRequest.Status.PENDING_INVESTIGATION,
    TeamRequest.Status.PENDING_PAYMENT,
    TeamRequest.Status.FINAL,
}


def _hash_token(token: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), token.encode(), sha256).hexdigest()


def participant_has_active_membership(competition: Competition, email: str) -> bool:
    return TeamMember.objects.filter(
        request__competition=competition,
        email__iexact=email,
        request__status__in=BLOCKING_STATUSES,
    ).exists()


# validate participant fields against competition config (raise specific codes)
def validate_participant_payload(cfg: CompetitionFieldConfig | None, payload: dict):
    def need(field):
        if not cfg:
            return FieldRequirement.REQUIRED
        return getattr(cfg, field)

    for field in [
        "first_name", "last_name", "email", "phone_number",
        "national_id", "student_card_image", "national_id_image", "tshirt_size",
    ]:
        mode = need(field)
        has_val = bool(payload.get(field))
        if mode == FieldRequirement.HIDDEN and has_val:
            raise CustomAPIException(
                code=EC.COMP_FIELD_INVALID,
                message=f"{field}: Field not allowed for this competition",
                status_code=400,
            )
        if mode == FieldRequirement.REQUIRED and not has_val:
            raise CustomAPIException(
                code=EC.COMP_FIELD_INVALID,
                message=f"{field}: Field is required",
                status_code=400,
            )


# --- public API --------------------------------------------------------------

@transaction.atomic
def submit_team_request(
        *, competition: Competition, submitter: User, team_name: str | None, participants: list[dict]
) -> TeamRequest:
    if (not submitter.is_authenticated) or (not getattr(submitter, "is_email_verified", False)):
        raise CustomAPIException(
            code=EC.ACC_EMAIL_NOT_VERIFIED,
            message="Login with verified email required",
            status_code=403,
        )

    # size check
    n = len(participants)
    if n < competition.min_team_size or n > competition.max_team_size:
        raise CustomAPIException(
            code=EC.COMP_TEAM_SIZE_INVALID,
            message=f"Team size must be between {competition.min_team_size} and {competition.max_team_size}",
            status_code=400,
        )

    cfg = getattr(competition, "field_config", None)

    # validate and block duplicates/actives
    seen_emails = set()
    for p in participants:
        validate_participant_payload(cfg, p)
        email = (p.get("email") or "").lower()
        if email in seen_emails:
            raise CustomAPIException(
                code=EC.COMP_DUPLICATE_PARTICIPANT_EMAIL,
                message="Duplicate participant email in payload",
                status_code=400,
            )
        seen_emails.add(email)
        if participant_has_active_membership(competition, email):
            raise CustomAPIException(
                code=EC.COMP_PARTICIPANT_ALREADY_ACTIVE,
                message=f"{email} is already on another active team for this competition",
                status_code=409,
            )

    tr = TeamRequest.objects.create(
        competition=competition,
        submitter=submitter,
        team_name=team_name or "",
        status=TeamRequest.Status.PENDING_APPROVAL,
    )

    # create members and tokens
    now = timezone.now()
    expires = now + timedelta(minutes=APPROVAL_TOKEN_TTL_MIN)
    for p in participants:
        token = secrets.token_urlsafe(24)
        TeamMember.objects.create(
            request=tr,
            user=submitter if (p.get("email", "").lower() == (submitter.email or "").lower()) else None,
            first_name=p.get("first_name", ""),
            last_name=p.get("last_name", ""),
            email=p.get("email", ""),
            phone_number=p.get("phone_number", ""),
            national_id=p.get("national_id", ""),
            student_card_image=p.get("student_card_image", ""),
            national_id_image=p.get("national_id_image", ""),
            tshirt_size=p.get("tshirt_size", ""),
            approval_token_hash=_hash_token(token),
            approval_token_expires_at=expires,
        )
        # email tokenized approval link
        send_status_change_email(
            to=p.get("email", ""),
            status_code="COMPETITION_MEMBER_APPROVAL",
            extra={
                "competition": competition.name,
                "team_name": team_name or "",
                "action_link": f"/api/competitions/approve?rid={tr.id}&token={token}",
            },
        )

    # notify submitter about submission
    send_status_change_email(
        to=submitter.email,
        status_code="COMPETITION_REQUEST_SUBMITTED",
        extra={"competition": competition.name, "team_name": team_name or ""},
    )

    return tr


@transaction.atomic
def approve_or_reject_member(*, request_id: int, token: str, accept: bool) -> TeamMember:
    try:
        member = TeamMember.objects.select_related("request", "request__competition").get(
            request_id=request_id, approval_token_hash=_hash_token(token)
        )
    except TeamMember.DoesNotExist:
        raise CustomAPIException(
            code=EC.COMP_INVALID_OR_EXPIRED_TOKEN,
            message="Invalid or expired token",
            status_code=400,
        )

    if member.approval_status != TeamMember.ApprovalStatus.PENDING:
        return member

    if member.approval_token_expires_at and member.approval_token_expires_at < timezone.now():
        raise CustomAPIException(
            code=EC.COMP_TOKEN_EXPIRED,
            message="Token expired",
            status_code=400,
        )

    member.approval_status = (
        TeamMember.ApprovalStatus.APPROVED if accept else TeamMember.ApprovalStatus.REJECTED
    )
    member.approval_at = timezone.now()
    member.approval_token_hash = ""
    member.save(update_fields=["approval_status", "approval_at", "approval_token_hash"])

    # if everyone approved → move to next status
    tr = member.request
    if tr.status == TeamRequest.Status.PENDING_APPROVAL:
        if tr.members.filter(approval_status=TeamMember.ApprovalStatus.REJECTED).exists():
            tr.status = TeamRequest.Status.REJECTED
            tr.save(update_fields=["status"])
            # notify submitter
            send_status_change_email(
                to=tr.submitter.email,
                status_code="COMPETITION_REQUEST_REJECTED",
                extra={"competition": tr.competition.name},
            )
        elif not tr.members.filter(approval_status=TeamMember.ApprovalStatus.PENDING).exists():
            # all approved
            if tr.competition.requires_backoffice_approval:
                tr.status = TeamRequest.Status.PENDING_INVESTIGATION
                tr.save(update_fields=["status"])
                send_status_change_email(
                    to=tr.submitter.email,
                    status_code="COMPETITION_REQUEST_PENDING_INVESTIGATION",
                    extra={"competition": tr.competition.name},
                )
            else:
                from payment.services import initiate_payment_for_target
                amount = int(tr.competition.signup_fee)
                try:
                    result = initiate_payment_for_target(
                        user=tr.submitter,
                        target_type="COMPETITION",
                        target_id=tr.id,
                        amount=amount,
                        description=f"Competition {tr.competition.name} #{tr.id}",
                    )
                except Exception as e:
                    raise CustomAPIException(
                        code=EC.COMP_PAYMENT_INIT_FAILED,
                        message=f"Payment initiate failed: {e}",
                        status_code=409,
                    )
                tr.payment_link = result.url
                tr.status = TeamRequest.Status.PENDING_PAYMENT
                tr.save(update_fields=["payment_link", "status"])
                send_status_change_email(
                    to=tr.submitter.email,
                    status_code="COMPETITION_REQUEST_PENDING_PAYMENT",
                    extra={"link": tr.payment_link},
                )

    return member


@transaction.atomic
def cancel_request(*, tr: TeamRequest, by_user: User):
    if tr.submitter_id != by_user.id:
        raise CustomAPIException(
            code=EC.COMP_ONLY_SUBMITTER_CAN_CANCEL,
            message="Only submitter can cancel",
            status_code=403,
        )
    if not tr.competition.requires_backoffice_approval:
        raise CustomAPIException(
            code=EC.COMP_CANCELLATION_NOT_APPLICABLE,
            message="Cancellation is only applicable for approval-mode competitions",
            status_code=400,
        )
    if tr.status not in {TeamRequest.Status.PENDING_APPROVAL, TeamRequest.Status.PENDING_INVESTIGATION}:
        raise CustomAPIException(
            code=EC.COMP_CANCELLATION_NOT_ALLOWED_STATE,
            message="Only pending requests can be cancelled",
            status_code=409,
        )

    tr.status = TeamRequest.Status.CANCELLED
    tr.save(update_fields=["status"])
    send_status_change_email(
        to=tr.submitter.email,
        status_code="COMPETITION_REQUEST_CANCELLED",
        extra={"competition": tr.competition.name},
    )
    return tr


# --- backoffice --------------------------------------------------------------

@transaction.atomic
def backoffice_approve_request(tr: TeamRequest) -> TeamRequest:
    if tr.status != TeamRequest.Status.PENDING_INVESTIGATION:
        raise CustomAPIException(
            code=EC.COMP_NOT_IN_INVESTIGATION_STATE,
            message="Request not in investigation state",
            status_code=409,
        )

    from payment.services import initiate_payment_for_target  # local import
    amount = int(tr.competition.signup_fee)
    try:
        result = initiate_payment_for_target(
            user=tr.submitter,
            target_type="COMPETITION",
            target_id=tr.id,
            amount=amount,
            description=f"Competition {tr.competition.name} #{tr.id}",
        )
    except Exception as e:
        raise CustomAPIException(
            code=EC.COMP_PAYMENT_INIT_FAILED,
            message=f"Payment initiate failed: {e}",
            status_code=409,
        )

    tr.payment_link = result.url
    tr.status = TeamRequest.Status.PENDING_PAYMENT
    tr.save(update_fields=["payment_link", "status"])
    send_status_change_email(
        to=tr.submitter.email,
        status_code="COMPETITION_REQUEST_PENDING_PAYMENT",
        extra={"link": tr.payment_link},
    )
    return tr


@transaction.atomic
def backoffice_reject_request(tr: TeamRequest, reason: str) -> TeamRequest:
    if tr.status not in {TeamRequest.Status.PENDING_INVESTIGATION, TeamRequest.Status.PENDING_APPROVAL}:
        raise CustomAPIException(
            code=EC.COMP_BACKOFFICE_REJECT_INVALID_STATE,
            message="Request not in a rejectable state",
            status_code=409,
        )
    tr.status = TeamRequest.Status.REJECTED
    tr.save(update_fields=["status"])
    # notify all members
    for m in tr.members.all():
        send_status_change_email(
            to=m.email,
            status_code="COMPETITION_REQUEST_REJECTED",
            extra={"competition": tr.competition.name, "reason": reason},
        )
    return tr


@transaction.atomic
def mark_payment_final(tr: TeamRequest) -> TeamRequest:
    tr.status = TeamRequest.Status.FINAL
    tr.save(update_fields=["status"])
    for m in tr.members.all():
        send_status_change_email(
            to=m.email,
            status_code="COMPETITION_REQUEST_FINAL",
            extra={"competition": tr.competition.name},
        )
    return tr


@transaction.atomic
def mark_payment_rejected(tr: TeamRequest) -> TeamRequest:
    tr.status = TeamRequest.Status.PAYMENT_REJECTED
    tr.save(update_fields=["status"])
    send_status_change_email(
        to=tr.submitter.email,
        status_code="COMPETITION_PAYMENT_REJECTED",
        extra={"competition": tr.competition.name},
    )
    return tr
