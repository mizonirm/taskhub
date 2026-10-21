"""
Creates (or updates) an admin account from environment variables.
Handy on hosts without shell access (e.g. Render free plan):
  ADMIN_USERNAME, ADMIN_EMAIL, ADMIN_PASSWORD
Safe to run on every deploy.
"""
import os

from django.core.management.base import BaseCommand

from accounts.models import User


class Command(BaseCommand):
    help = "Create/update the admin user from ADMIN_* environment variables."

    def handle(self, *args, **opts):
        username = os.environ.get("ADMIN_USERNAME")
        email = os.environ.get("ADMIN_EMAIL")
        password = os.environ.get("ADMIN_PASSWORD")
        if not (username and email and password):
            self.stdout.write("ADMIN_* variables not set; skipping.")
            return
        user, created = User.objects.get_or_create(username=username, defaults={"email": email})
        user.email = email
        user.is_staff = user.is_superuser = user.is_active = True
        user.set_password(password)
        user.save()
        self.stdout.write(f"Admin '{username}' {'created' if created else 'updated'}.")
