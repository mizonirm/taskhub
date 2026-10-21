from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from projects import permissions as perm
from projects.models import Project, ProjectRequest, Task
from projects.notifications import notify
from projects.reminders import generate_due_reminders
from .forms import OTPVerifyForm, SignupForm
from .models import User


def health(request):
    """Cheap endpoint for uptime monitors / host health checks (no login, no database)."""
    return HttpResponse("ok", content_type="text/plain")


def home(request):
    return redirect("dashboard" if request.user.is_authenticated else "login")


def signup(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save(commit=False)
        user.is_active = False  # locked until the email is verified
        user.save()
        user.generate_otp()
        request.session["pending_user_id"] = user.id
        messages.info(request, "We've sent a 6-digit verification code to your email.")
        return redirect("verify_otp")
    return render(request, "accounts/signup.html", {"form": form})


def verify_otp(request):
    user_id = request.session.get("pending_user_id")
    if not user_id:
        return redirect("signup")
    user = get_object_or_404(User, id=user_id)
    form = OTPVerifyForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        ok, error = user.check_otp(form.cleaned_data["code"])
        if ok:
            user.is_email_verified = True
            user.otp_code = ""
            del request.session["pending_user_id"]
            if user.role == "faculty" and settings.FACULTY_REQUIRES_APPROVAL:
                # Faculty can approve projects, so a human admin must vouch for them first.
                user.is_active = False
                user.save()
                admins = User.objects.filter(is_active=True).filter(role="admin") | \
                    User.objects.filter(is_active=True, is_superuser=True)
                notify(list(admins), f"New faculty signup awaiting approval: {user.display_name} ({user.email}).",
                       reverse("admin:accounts_user_change", args=[user.pk]))
                return render(request, "accounts/pending_approval.html", {"pending_user": user})
            user.is_active = True
            user.save()
            login(request, user)
            messages.success(request, "Email verified. Welcome to TaskHub!")
            return redirect("dashboard")
        form.add_error("code", error)
    # Showcase sites with no email configured: show the code on screen so a reviewer isn't stuck.
    show_code = settings.DEMO_MODE and settings.EMAIL_BACKEND.endswith("console.EmailBackend")
    return render(request, "accounts/verify_otp.html", {
        "form": form, "pending_user": user, "demo_otp": user.otp_code if show_code else None})


@require_POST
def resend_otp(request):
    user_id = request.session.get("pending_user_id")
    if not user_id:
        return redirect("signup")
    user = get_object_or_404(User, id=user_id)
    user.generate_otp()
    messages.info(request, "A new code has been sent.")
    return redirect("verify_otp")


@login_required
def dashboard(request):
    user = request.user
    generate_due_reminders(user)
    ctx = {
        "notifications": user.notifications.filter(is_read=False)[:8],
    }
    if perm.is_admin(user):
        ctx["active_projects"] = Project.objects.filter(status="in_progress")
        ctx["pending_requests"] = ProjectRequest.objects.filter(status="pending")
        ctx["closure_requests"] = Project.objects.filter(status="closure_requested")
    elif user.role == "faculty":
        ctx["active_projects"] = Project.objects.filter(faculty=user, status="in_progress")
        ctx["pending_requests"] = ProjectRequest.objects.filter(faculty=user, status="pending")
        ctx["closure_requests"] = Project.objects.filter(faculty=user, status="closure_requested")
    else:
        ctx["active_projects"] = Project.objects.filter(members__user=user, status="in_progress").distinct()
        ctx["my_tasks"] = (Task.objects.filter(assigned_to=user, project__status="in_progress")
                           .exclude(status="completed").select_related("project").order_by("due_date"))
        ctx["my_requests"] = ProjectRequest.objects.filter(requested_by=user, status="pending")
    return render(request, "accounts/dashboard.html", ctx)
