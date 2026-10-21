import random
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.mail import send_mail
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    """
    Roles are chosen at signup (faculty / member). Admins are superusers:
    `createsuperuser` automatically gives them role='admin'.
    "Project Lead" is not a global role — it is per project (see ProjectMembership).
    """

    ROLE_CHOICES = [
        ("admin", "Admin"),
        ("faculty", "Faculty"),
        ("member", "Team Member"),
    ]

    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default="member")
    email = models.EmailField(unique=True)

    is_email_verified = models.BooleanField(default=False)
    otp_code = models.CharField(max_length=6, blank=True, null=True)
    otp_created_at = models.DateTimeField(null=True, blank=True)
    otp_attempts = models.PositiveSmallIntegerField(default=0)

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.role = "admin"
            self.is_email_verified = True
        super().save(*args, **kwargs)

    @property
    def is_admin_role(self):
        return self.role == "admin" or self.is_superuser

    @property
    def display_name(self):
        return self.get_full_name() or self.username

    # ---- OTP ------------------------------------------------------------
    def generate_otp(self):
        code = f"{random.SystemRandom().randint(0, 999999):06d}"
        self.otp_code = code
        self.otp_created_at = timezone.now()
        self.otp_attempts = 0
        self.save(update_fields=["otp_code", "otp_created_at", "otp_attempts"])

        send_mail(
            subject="Your TaskHub verification code",
            message=(
                f"Hi {self.display_name},\n\nYour TaskHub verification code is {code}.\n"
                f"It is valid for {settings.OTP_VALID_MINUTES} minutes.\n"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[self.email],
            fail_silently=False,
        )
        if settings.EMAIL_BACKEND.endswith("console.EmailBackend"):
            print(f"\n[TaskHub OTP] Verification code for {self.email}: {code}\n")
        return code

    def check_otp(self, code):
        """Returns (ok, error_message)."""
        if not self.otp_code or not self.otp_created_at:
            return False, "No active code. Please request a new one."
        if self.otp_attempts >= settings.OTP_MAX_ATTEMPTS:
            return False, "Too many incorrect attempts. Please request a new code."
        if timezone.now() - self.otp_created_at > timedelta(minutes=settings.OTP_VALID_MINUTES):
            return False, "This code has expired. Please request a new one."
        if code != self.otp_code:
            self.otp_attempts += 1
            self.save(update_fields=["otp_attempts"])
            return False, "Incorrect code. Please try again."
        return True, ""

    def __str__(self):
        return f"{self.display_name} ({self.get_role_display()})"
