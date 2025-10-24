from django.contrib import admin
from django.utils import timezone
from .models import Competition, CompetitionFieldConfig, TeamRequest, TeamMember
from .services import (
    backoffice_approve_request, backoffice_reject_request,
    mark_payment_final, cancel_request,
)

class FieldConfigInline(admin.StackedInline):
    model = CompetitionFieldConfig
    extra = 0

@admin.register(Competition)
class CompetitionAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "min_team_size", "max_team_size", "signup_fee_aut", "signup_fee_base", "requires_backoffice_approval", "is_active")
    search_fields = ("name", "slug")
    inlines = [FieldConfigInline]

class TeamMemberInline(admin.TabularInline):
    model = TeamMember
    extra = 0

@admin.register(TeamRequest)
class TeamRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "competition", "team_name", "submitter", "status", "created_at")
    list_filter = ("status", "competition")
    search_fields = ("team_name", "submitter__email")
    inlines = [TeamMemberInline]

    actions = ["approve_selected", "reject_selected", "mark_final_selected"]

    def approve_selected(self, request, queryset):
        count = 0
        for tr in queryset.select_related("competition", "submitter"):
            backoffice_approve_request(tr)
            count += 1
        self.message_user(request, f"Approved {count} request(s)")
    approve_selected.short_description = "Approve → send payment link"

    def reject_selected(self, request, queryset):
        count = 0
        for tr in queryset:
            backoffice_reject_request(tr, reason=getattr(tr, "_tmp_reject_reason", "Rejected"))
            count += 1
        self.message_user(request, f"Rejected {count} request(s)")
    reject_selected.short_description = "Reject with reason (set on object)"

    def mark_final_selected(self, request, queryset):
        count = 0
        for tr in queryset:
            mark_payment_final(tr)
            count += 1
        self.message_user(request, f"Marked FINAL for {count} request(s)")
    mark_final_selected.short_description = "Mark paid (FINAL)"