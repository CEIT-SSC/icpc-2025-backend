from django.contrib import admin
from django.utils import timezone

from .models import Course, Presenter, ScheduleRule, Registration
from .services import set_status_approved, set_status_rejected, set_status_final




class ScheduleInline(admin.TabularInline):
    model = ScheduleRule
    extra = 0




@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("name", "subtitle", "capacity", "price", "is_active")
    search_fields = ("name", "subtitle")
    inlines = [ScheduleInline]
    filter_horizontal = ("presenters",)




@admin.register(Presenter)
class PresenterAdmin(admin.ModelAdmin):
    list_display = ("full_name", "email", "website")
    search_fields = ("full_name", "email")




@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    """
    Enriched Registration admin with user's full data in list & detail views.
    """
    
    list_display = (
        "id",
        "course",
        "user_email",
        "user_full_name",
        "user_phone",
        "status",
        "submitted_at",
        "decided_at",
    )
    list_select_related = ("user", "course")
    list_filter = ("status", "course")
    search_fields = (
        "course__name",
        "course__slug",
        "user__email",
        "user__first_name",
        "user__last_name",
        "user__phone_number",
    )
    ordering = ("-submitted_at",)
    date_hierarchy = "submitted_at"

    
    raw_id_fields = ("user", "course")

    
    readonly_fields = (
        "user_email",
        "user_first_name",
        "user_last_name",
        "user_phone",
        "submitted_at",
        "decided_at",
        "payment_link",
    )

    
    fieldsets = (
        ("Registration", {
            "fields": (
                "course",
                "user",
                "status",
                "is_final",
                "payment_link",
                "rejection_reason",
            )
        }),
        ("Timestamps", {
            "fields": ("submitted_at", "decided_at"),
        }),
        ("User (read-only)", {
            "fields": (
                "user_email",
                "user_first_name",
                "user_last_name",
                "user_phone",
            )
        }),
    )

    
    actions = ("approve_selected", "reject_selected", "finalize_selected")

    

    @admin.display(ordering="user__email", description="User email")
    def user_email(self, obj: Registration) -> str:
        return getattr(obj.user, "email", "") or ""

    @admin.display(description="User name")
    def user_full_name(self, obj: Registration) -> str:
        fn = (getattr(obj.user, "first_name", "") or "").strip()
        ln = (getattr(obj.user, "last_name", "") or "").strip()
        return f"{fn} {ln}".strip() or "(no name)"

    @admin.display(description="First name")
    def user_first_name(self, obj: Registration) -> str:
        return getattr(obj.user, "first_name", "") or ""

    @admin.display(description="Last name")
    def user_last_name(self, obj: Registration) -> str:
        return getattr(obj.user, "last_name", "") or ""

    @admin.display(ordering="user__phone_number", description="Phone")
    def user_phone(self, obj: Registration) -> str:
        return getattr(obj.user, "phone_number", "") or ""

    

    def approve_selected(self, request, queryset):
        count = 0
        for reg in queryset.select_related("course", "user"):
            set_status_approved(reg, actor=request.user)
            count += 1
        self.message_user(request, f"Approved {count} registration(s)")
    approve_selected.short_description = "Approve (and issue payment link if applicable)"

    def reject_selected(self, request, queryset):
        count = 0
        for reg in queryset.select_related("course", "user"):
            
            if not reg.rejection_reason:
                continue
            set_status_rejected(reg, actor=request.user)
            count += 1
        self.message_user(request, f"Rejected {count} registration(s)")
    reject_selected.short_description = "Reject (requires rejection_reason)"

    def finalize_selected(self, request, queryset):
        count = 0
        for reg in queryset.select_related("course", "user"):
            set_status_final(reg, actor=request.user)
            count += 1
        self.message_user(request, f"Marked {count} registration(s) as paid")
    finalize_selected.short_description = "Mark paid (FINAL)"
