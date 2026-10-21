from django.conf import settings


def notifications(request):
    ctx = {"demo_mode": settings.DEMO_MODE, "demo_password": settings.DEMO_PASSWORD}
    if request.user.is_authenticated:
        ctx["unread_count"] = request.user.notifications.filter(is_read=False).count()
    return ctx
