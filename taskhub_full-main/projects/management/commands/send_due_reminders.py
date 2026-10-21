"""
Optional: generate due-date reminders for everyone in one go (e.g. a daily scheduled job):
    python manage.py send_due_reminders
Reminders are ALSO generated automatically when a user opens their dashboard, so this is only
needed if you want people notified without them logging in. Safe to run repeatedly.
"""
from django.core.management.base import BaseCommand

from accounts.models import User
from projects.models import Notification
from projects.reminders import generate_due_reminders


class Command(BaseCommand):
    help = "Create due-date / overdue reminder notifications for all active users."

    def handle(self, *args, **opts):
        before = Notification.objects.count()
        for user in User.objects.filter(is_active=True, is_superuser=False):
            generate_due_reminders(user)
        self.stdout.write(f"{Notification.objects.count() - before} reminder(s) created.")
