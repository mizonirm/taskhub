from .models import Notification


def notify(users, message, link=""):
    """Create one notification per (unique) user."""
    seen = set()
    for user in users:
        if user is None or user.pk in seen:
            continue
        seen.add(user.pk)
        Notification.objects.create(user=user, message=message[:300], link=link)
