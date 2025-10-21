from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

User = settings.AUTH_USER_MODEL

class Competition(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    description = models.TextField(blank=True)

    # team size (set both to 1 for individual)
    min_team_size = models.PositiveSmallIntegerField(default=1)
    max_team_size = models.PositiveSmallIntegerField(default=1)

    signup_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    requires_backoffice_approval = models.BooleanField(default=True)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:220]
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class FieldRequirement(models.TextChoices):
    REQUIRED = "REQ", "Required"
    OPTIONAL = "OPT", "Optional"
    HIDDEN = "HID", "Hidden"

class CompetitionFieldConfig(models.Model):
    """Controls which participant fields are required/optional/hidden for a competition."""
    competition = models.OneToOneField(Competition, on_delete=models.CASCADE, related_name="field_config")

    first_name = models.CharField(max_length=3, choices=FieldRequirement.choices, default=FieldRequirement.REQUIRED)
    last_name = models.CharField(max_length=3, choices=FieldRequirement.choices, default=FieldRequirement.REQUIRED)
    national_id = models.CharField(max_length=3, choices=FieldRequirement.choices, default=FieldRequirement.OPTIONAL)
    student_number = models.CharField(max_length=3, choices=FieldRequirement.choices, default=FieldRequirement.OPTIONAL)
    student_card_image = models.CharField(max_length=3, choices=FieldRequirement.choices, default=FieldRequirement.OPTIONAL)
    national_id_image = models.CharField(max_length=3, choices=FieldRequirement.choices, default=FieldRequirement.OPTIONAL)
    tshirt_size = models.CharField(max_length=3, choices=FieldRequirement.choices, default=FieldRequirement.OPTIONAL)
    phone_number = models.CharField(max_length=3, choices=FieldRequirement.choices, default=FieldRequirement.REQUIRED)
    email = models.CharField(max_length=3, choices=FieldRequirement.choices, default=FieldRequirement.REQUIRED)
    university_name = models.CharField(max_length=3, choices=FieldRequirement.choices, default=FieldRequirement.OPTIONAL)

    def __str__(self):
        return f"FieldConfig<{self.competition_id}>"

class TeamRequest(models.Model):
    class Status(models.TextChoices):
        PENDING_APPROVAL = "PENDING_APPROVAL", "Pending – awaiting members' email approvals"
        PENDING_INVESTIGATION = "PENDING_INVESTIGATION", "Pending – backoffice investigation"
        PENDING_PAYMENT = "PENDING_PAYMENT", "Pending payment"
        FINAL = "FINAL", "Finalized"
        PAYMENT_REJECTED = "PAYMENT_REJECTED", "Payment rejected"
        REJECTED = "REJECTED", "Rejected"
        CANCELLED = "CANCELLED", "Cancelled by submitter"

    competition = models.ForeignKey(Competition, on_delete=models.CASCADE, related_name="team_requests")
    submitter = models.ForeignKey(User, on_delete=models.CASCADE, related_name="submitted_team_requests")
    team_name = models.CharField(max_length=120, blank=True)

    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PENDING_APPROVAL)
    payment_link = models.URLField(blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["competition", "status"])]

    def __str__(self):
        return f"TeamRequest<{self.id}:{self.competition.slug}:{self.status}>"

class TeamMember(models.Model):
    class ApprovalStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    request = models.ForeignKey(TeamRequest, on_delete=models.CASCADE, related_name="members")
    # NOTE: only submitter is a user; others are guests identified by email
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="competition_memberships")

    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    email = models.EmailField()
    phone_number = models.CharField(max_length=30)
    national_id = models.CharField(max_length=50, blank=True)
    student_card_image = models.URLField(blank=True)
    national_id_image = models.URLField(blank=True)
    tshirt_size = models.CharField(max_length=10, blank=True)
    university_name = models.CharField(max_length=120, blank=True)
    student_number = models.CharField(max_length=15, blank=True)

    approval_status = models.CharField(max_length=10, choices=ApprovalStatus.choices, default=ApprovalStatus.PENDING)
    approval_token_hash = models.CharField(max_length=64, blank=True)  # sha256 hex
    approval_token_expires_at = models.DateTimeField(null=True, blank=True)
    approval_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ("request", "email")

    def __str__(self):
        return f"Member<{self.email}:{self.approval_status}>"