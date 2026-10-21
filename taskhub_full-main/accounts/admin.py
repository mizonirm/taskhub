from django.conf import settings
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.core.mail import send_mail

from .models import User


@admin.register(User)
class TaskHubUserAdmin(UserAdmin):
    list_display = ("username", "email", "role", "is_email_verified", "is_active", "is_staff")
    list_filter = ("role", "is_email_verified", "is_active")
    fieldsets = UserAdmin.fieldsets + (("TaskHub", {"fields": ("role", "is_email_verified")}),)
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("TaskHub", {"fields": ("email", "role", "is_email_verified")}),
    )
    actions = ["approve_faculty"]

    @admin.action(description="Approve selected faculty accounts (they can then log in)")
    def approve_faculty(self, request, queryset):
        pending = queryset.filter(role="faculty", is_email_verified=True, is_active=False)
        count = 0
        for user in pending:
            user.is_active = True
            user.save(update_fields=["is_active"])
            send_mail(
                "Your TaskHub faculty account was approved",
                f"Hi {user.display_name},\n\nYour faculty account has been approved. You can log in now.",
                settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=True,
            )
            count += 1
        self.message_user(request, f"Approved {count} faculty account(s).", messages.SUCCESS)
