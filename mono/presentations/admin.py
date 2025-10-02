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
    list_display = ("user", "course", "status", "submitted_at", "decided_at")
    list_filter = ("status", "course")
    search_fields = ("user__email",)
    actions = [
        "approve_selected", "reject_selected", "finalize_selected",
    ]

    def approve_selected(self, request, queryset):
        count = 0
        print(request.user.email)
        for reg in queryset.select_related("course", "user"):
            set_status_approved(reg, actor=request.user)
            count += 1
        self.message_user(request, f"Approved {count} registration(s)")
    approve_selected.short_description = "Approve and email payment link"

    def reject_selected(self, request, queryset):
        count = 0
        for reg in queryset.select_related("course", "user"):
            # rejection reason must be set per object; if blank, skip
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
        self.message_user(request, f"Finalized {count} registration(s)")
    finalize_selected.short_description = "Mark paid (FINAL)"