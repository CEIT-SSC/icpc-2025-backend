# Register your models here.
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User, UserExtraData


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    model = User
    list_display = ("email", "first_name", "last_name", "phone_number", "is_email_verified", "is_staff")
    list_filter = ("is_email_verified", "is_staff", "is_superuser")
    ordering = ("email",)
    search_fields = ("email", "first_name", "last_name")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "phone_number")}),
        ("Permissions",
         {"fields": ("is_active", "is_staff", "is_superuser", "is_email_verified", "groups", "user_permissions")}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "password1", "password2", "is_staff", "is_superuser", "is_email_verified"),
        }),
    )


@admin.register(UserExtraData)
class UserExtraDataAdmin(admin.ModelAdmin):
    list_display = ("user", "codeforces_handle", "codeforces_score", "updated_at")
    search_fields = ("user__email", "codeforces_handle")
