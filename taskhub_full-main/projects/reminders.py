"""Due-date reminders, generated when a user opens their dashboard (no scheduler needed).

Each reminder text is unique per task/project + due date, so it is only created once.
"""
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from .models import Notification, Project, Task

REMINDER_DAYS = 3


def _create_once(user, message, link):
    if not Notification.objects.filter(user=user, message=message).exists():
        Notification.objects.create(user=user, message=message[:300], link=link)


def generate_due_reminders(user):
    horizon = timezone.localdate() + timedelta(days=REMINDER_DAYS)
    today = timezone.localdate()

    tasks = (Task.objects.filter(assigned_to=user, project__status="in_progress",
                                 due_date__isnull=False, due_date__lte=horizon)
             .exclude(status="completed").select_related("project"))
    for t in tasks:
        when = f"{t.due_date:%d %b %Y}"
        text = (f"Overdue: {t.display_id} '{t.title}' was due on {when}." if t.due_date < today
                else f"Reminder: {t.display_id} '{t.title}' is due on {when}.")
        _create_once(user, text, f"{reverse('task_detail', args=[t.pk])}")

    if user.role == "member":
        projects = Project.objects.filter(members__user=user, status="in_progress",
                                          due_date__lte=horizon).distinct()
        for p in projects:
            when = f"{p.due_date:%d %b %Y}"
            text = (f"Overdue: project '{p.name}' was due on {when}." if p.due_date < today
                    else f"Reminder: project '{p.name}' is due on {when}.")
            _create_once(user, text, reverse("project_detail", args=[p.pk]))
