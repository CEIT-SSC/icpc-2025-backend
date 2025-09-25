from django.contrib import admin
from .models import EmailTemplate, Notification, BulkJob, BulkRecipient

# Register your models here.
@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ("code", "subject", "updated_at")
    search_fields = ("code", "subject")

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("channel", "to", "status", "sent_at", "created_at")
    list_filter = ("channel", "status")
    search_fields = ("to", "subject_override")

class BulkRecipientInline(admin.TabularInline):
    model = BulkRecipient
    extra = 0

@admin.register(BulkJob)
class BulkJobAdmin(admin.ModelAdmin):
    list_display = ("id", "job_type", "status", "total", "sent", "failed", "created_at")
    inlines = [BulkRecipientInline]