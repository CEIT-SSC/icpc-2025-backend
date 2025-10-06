from django.conf import settings
from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.utils.text import slugify

User = settings.AUTH_USER_MODEL


class Presenter(models.Model):
    full_name = models.CharField(max_length=120)
    bio = models.TextField(blank=True)
    email = models.EmailField(blank=True)
    website = models.URLField(blank=True)

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name


class Course(models.Model):
    name = models.CharField(max_length=200)
    subtitle = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    presenters = models.ManyToManyField(Presenter, related_name="courses", blank=True)

    start_date = models.DateField(null=True, blank=True)
    online = models.BooleanField(default=True)
    onsite = models.BooleanField(default=False)
    classes_count = models.PositiveIntegerField(default=0)

    capacity = models.PositiveIntegerField(default=0)
    price = models.IntegerField(validators=[MinValueValidator(0)])

    children = models.ManyToManyField(
        "self",
        symmetrical=False,
        related_name="parents",
        blank=True,
    )

    requires_approval = models.BooleanField(
        default=True,
        help_text="If off, registrations auto-approve (or finalize if price=0).",
    )

    slug = models.SlugField(max_length=220, unique=True, blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:220]
        return super().save(*args, **kwargs)

    def remained_capacity(self) -> int:
        from .models import Registration  # local import to avoid cycles

        finalized_as_parent = self.registrations.filter(
            status=Registration.Status.FINAL
        ).count()

        finalized_as_child = self.registration_items.filter(
            registration__status=Registration.Status.FINAL
        ).count()

        used = finalized_as_parent + finalized_as_child
        cap = self.capacity or 0
        return max(cap - used, 0)

    def __str__(self):
        return self.name


class ScheduleRule(models.Model):
    class Weekday(models.IntegerChoices):
        MON = 0, "Mon"
        TUE = 1, "Tue"
        WED = 2, "Wed"
        THU = 3, "Thu"
        FRI = 4, "Fri"
        SAT = 5, "Sat"
        SUN = 6, "Sun"

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="schedule")
    weekday = models.IntegerField(choices=Weekday.choices)
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        ordering = ["weekday", "start_time"]
        unique_together = ("course", "weekday", "start_time", "end_time")

    def __str__(self):
        return f"{self.get_weekday_display()} {self.start_time}-{self.end_time}"


class Registration(models.Model):
    class Status(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Submitted"
        RESERVED = "RESERVED", "Reserved"   # capacity full -> RESERVED
        QUEUED = "QUEUED", "Queued"         # capacity available -> QUEUED
        APPROVED = "APPROVED", "Approved"
        FINAL = "FINAL", "Finalized"
        REJECTED = "REJECTED", "Rejected"
        CANCELLED = "CANCELLED", "Cancelled"

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="registrations")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="course_registrations")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.SUBMITTED)

    # optional resume link or blob pointer
    resume_url = models.URLField(blank=True)

    # set by backoffice on reject
    rejection_reason = models.TextField(blank=True)

    # set by backoffice on approve; payment app will generate proper link later
    payment_link = models.URLField(blank=True)

    submitted_at = models.DateTimeField(default=timezone.now)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("course", "user")
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"Reg<{self.user_id}:{self.course.slug}:{self.status}>"


class RegistrationItem(models.Model):
    """
    Child presentation selection for a given registration.
    """
    registration = models.ForeignKey(
        Registration, on_delete=models.CASCADE, related_name="items"
    )
    child_course = models.ForeignKey(
        Course, on_delete=models.PROTECT, related_name="registration_items"
    )
    price = models.IntegerField(validators=[MinValueValidator(0)])
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ("registration", "child_course")

    def __str__(self):
        return f"RegItem<{self.registration_id}:{self.child_course.slug}:{self.price}>"
