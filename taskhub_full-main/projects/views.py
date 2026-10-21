import mimetypes
import os
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import content_disposition_header, url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from . import permissions as perm
from .forms import (AddMemberForm, CommentForm, DocumentForm, ProjectEditForm,
                    ProjectRequestForm, TaskForm)
from .models import (Comment, Document, Notification, Project, ProjectMembership,
                     ProjectRequest, Task)
from .notifications import notify

UPCOMING_DAYS = 14


def _safe_next(request, fallback):
    """Only follow a 'next' address that points back to this site."""
    target = request.POST.get("next") or ""
    ok = url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()},
                                         require_https=request.is_secure())
    return target if ok else fallback


def _project_url(project, tab="details"):
    return f"{reverse('project_detail', args=[project.pk])}?tab={tab}"


def _task_url(task, tab="details"):
    return f"{reverse('task_detail', args=[task.pk])}?tab={tab}"


def _get_project(request, pk, *, manage=False, contribute=False):
    project = get_object_or_404(Project, pk=pk)
    if not perm.can_view(request.user, project):
        raise PermissionDenied("You are not part of this project.")
    if manage and not perm.can_manage(request.user, project):
        raise PermissionDenied("Only the project lead can do this (and not while the project is read-only).")
    if contribute and not perm.can_contribute(request.user, project):
        raise PermissionDenied("This project is read-only.")
    return project


# ---------------------------------------------------------------- requests ----
@login_required
def request_project(request):
    if request.user.role != "member":
        raise PermissionDenied("Only team members can request new projects.")
    form = ProjectRequestForm(request.POST or None, initial={"project_lead": request.user})
    if request.method == "POST" and form.is_valid():
        req = form.save(commit=False)
        req.requested_by = request.user
        req.save()
        notify([req.faculty],
               f"{request.user.display_name} requested a new project: '{req.name}'. Please review.",
               reverse("dashboard"))
        messages.success(request, "Project request submitted for faculty approval.")
        return redirect("dashboard")
    return render(request, "projects/request_form.html", {"form": form})


@login_required
@require_POST
def review_request(request, pk, decision):
    req = get_object_or_404(ProjectRequest, pk=pk)
    if not (req.faculty_id == request.user.id or perm.is_admin(request.user)):
        raise PermissionDenied("Only the assigned faculty can review this request.")
    if req.status != "pending":
        messages.warning(request, "This request has already been reviewed.")
        return redirect("dashboard")

    if decision == "approve":
        req.status = "approved"
        req.save()
        project = Project.objects.create(
            name=req.name, description=req.description, due_date=req.due_date,
            project_lead=req.project_lead, faculty=req.faculty, source_request=req,
        )
        # Project.save() already made the lead a member (is_lead=True); add the requester too.
        if req.requested_by_id != req.project_lead_id:
            ProjectMembership.objects.get_or_create(project=project, user=req.requested_by)
        link = _project_url(project)
        notify([req.requested_by], f"Your project request '{req.name}' was approved.", link)
        if req.project_lead_id != req.requested_by_id:
            notify([req.project_lead], f"You are the project lead of '{req.name}'.", link)
        messages.success(request, f"Approved. '{project.name}' is now active.")
    elif decision == "deny":
        req.status = "denied"
        req.save()
        notify([req.requested_by], f"Your project request '{req.name}' was denied.", reverse("dashboard"))
        messages.info(request, f"Request '{req.name}' denied.")
    else:
        raise PermissionDenied("Unknown decision.")
    return redirect("dashboard")


# ---------------------------------------------------------------- projects ----
@login_required
def project_list(request):
    tab = request.GET.get("tab", "all")
    qs = perm.visible_projects(request.user, Project.objects.select_related("project_lead", "faculty"))
    today = timezone.localdate()
    counts = {
        "all": qs.count(),
        "active": qs.filter(status="in_progress").count(),
        "upcoming": qs.filter(status="in_progress", due_date__gte=today,
                              due_date__lte=today + timedelta(days=UPCOMING_DAYS)).count(),
        "closed": qs.filter(status="closed").count(),
    }
    if tab == "active":
        qs = qs.filter(status="in_progress")
    elif tab == "upcoming":
        qs = qs.filter(status="in_progress", due_date__gte=today,
                       due_date__lte=today + timedelta(days=UPCOMING_DAYS))
    elif tab == "closed":
        qs = qs.filter(status="closed")
    else:
        tab = "all"
    return render(request, "projects/project_list.html", {
        "projects": qs.order_by("due_date"), "tab": tab, "counts": counts,
        "upcoming_days": UPCOMING_DAYS,
    })


@login_required
def project_detail(request, pk):
    project = _get_project(request, pk)
    tab = request.GET.get("tab", "details")
    if tab not in ("details", "tasks", "comments", "documents"):
        tab = "details"

    can_manage = perm.can_manage(request.user, project)
    lead_or_admin = perm.is_admin(request.user) or perm.is_lead(request.user, project)
    ctx = {
        "project": project, "tab": tab, "can_manage": can_manage,
        "lead_or_admin": lead_or_admin,
        "can_contribute": perm.can_contribute(request.user, project),
        "is_project_faculty": perm.is_project_faculty(request.user, project),
        "members": project.members.select_related("user"),
        "tab_counts": {
            "tasks": project.tasks.filter(parent__isnull=True).count(),
            "comments": project.comments.filter(task__isnull=True).count(),
            "documents": project.documents.count(),
        },
    }
    if tab == "tasks":
        ctx["tasks"] = (project.tasks.filter(parent__isnull=True)
                        .prefetch_related("assigned_to", "subtasks").order_by("due_date", "id"))
    elif tab == "comments":
        ctx["comments"] = project.comments.filter(task__isnull=True).select_related("author")
        ctx["comment_form"] = CommentForm()
    elif tab == "documents":
        ctx["documents"] = project.documents.defer("data").select_related("uploaded_by")
        ctx["document_form"] = DocumentForm()
    else:
        ctx["add_member_form"] = AddMemberForm(project=project) if can_manage else None
    return render(request, "projects/project_detail.html", ctx)


@login_required
def project_edit(request, pk):
    project = _get_project(request, pk, manage=True)
    form = ProjectEditForm(request.POST or None, instance=project)
    if request.method == "POST" and form.is_valid():
        form.save()
        notify(project.member_users() - {request.user}, f"Project '{project.name}' was updated.",
               _project_url(project))
        messages.success(request, "Project updated.")
        return redirect(_project_url(project))
    return render(request, "projects/project_edit.html", {"form": form, "project": project})


@login_required
@require_POST
def project_delete(request, pk):
    project = _get_project(request, pk, manage=True)
    notify(project.member_users() - {request.user}, f"Project '{project.name}' was deleted.", "")
    name = project.name
    project.delete()
    messages.success(request, f"Project '{name}' deleted.")
    return redirect("project_list")


@login_required
@require_POST
def member_add(request, pk):
    project = _get_project(request, pk, manage=True)
    form = AddMemberForm(request.POST, project=project)
    if form.is_valid():
        user = form.cleaned_data["user"]
        ProjectMembership.objects.get_or_create(project=project, user=user)
        notify([user], f"You were added to the project '{project.name}'.", _project_url(project))
        messages.success(request, f"{user.display_name} added to the team.")
    else:
        messages.error(request, "Could not add that member.")
    return redirect(_project_url(project))


@login_required
@require_POST
def member_remove(request, pk, user_id):
    project = _get_project(request, pk, manage=True)
    membership = get_object_or_404(ProjectMembership, project=project, user_id=user_id)
    if membership.is_lead:
        messages.error(request, "The project lead can't be removed.")
    else:
        for task in Task.objects.filter(project=project, assigned_to=membership.user):
            task.assigned_to.remove(membership.user)
        notify([membership.user], f"You were removed from the project '{project.name}'.", "")
        membership.delete()
        messages.success(request, "Member removed.")
    return redirect(_project_url(project))


@login_required
@require_POST
def project_status(request, pk):
    """Close / request closure / reopen / approve closure / deny closure."""
    project = _get_project(request, pk)
    action = request.POST.get("action")
    user = request.user
    lead_or_admin = perm.is_admin(user) or perm.is_lead(user, project)
    faculty_ok = perm.is_project_faculty(user, project) or perm.is_admin(user)
    everyone = project.member_users() - {user}
    link = _project_url(project)

    if action == "close" and lead_or_admin and project.status == "in_progress":
        if project.percent_complete < 100:
            messages.error(request, "Project isn't 100% complete. Use 'Request closure' to ask faculty.")
        else:
            project.status = "closed"
            project.save(update_fields=["status"])
            notify(everyone, f"Project '{project.name}' was closed.", link)
            messages.success(request, "Project closed.")
    elif action == "request_closure" and lead_or_admin and project.status == "in_progress":
        if project.percent_complete >= 100:
            messages.error(request, "Project is 100% complete — you can close it directly.")
        else:
            project.status = "closure_requested"
            project.save(update_fields=["status"])
            notify([project.faculty], f"Closure requested for '{project.name}' "
                   f"({project.percent_complete:g}% complete). Please review.", link)
            notify(everyone - {project.faculty}, f"Closure was requested for '{project.name}'.", link)
            messages.success(request, "Closure requested. The project is read-only until faculty responds.")
    elif action == "approve_closure" and faculty_ok and project.status == "closure_requested":
        project.status = "closed"
        project.save(update_fields=["status"])
        notify(everyone, f"Closure of '{project.name}' was approved. The project is now closed.", link)
        messages.success(request, "Closure approved.")
    elif action == "deny_closure" and faculty_ok and project.status == "closure_requested":
        project.status = "in_progress"
        project.save(update_fields=["status"])
        notify(everyone, f"Closure of '{project.name}' was not approved. The project is back in progress.", link)
        messages.info(request, "Closure denied. Project is back in progress.")
    elif action == "reopen" and lead_or_admin and project.status == "closed":
        project.status = "in_progress"
        project.save(update_fields=["status"])
        notify(everyone, f"Project '{project.name}' was reopened.", link)
        messages.success(request, "Project reopened.")
    else:
        raise PermissionDenied("That action isn't available right now.")
    return redirect(link)


# ------------------------------------------------------------------- tasks ----
def _notify_new_assignees(task, previous_ids):
    new_users = [u for u in task.assigned_to.all() if u.id not in previous_ids]
    due = f" Due {task.due_date:%d %b %Y}." if task.due_date else ""
    notify(new_users, f"You were assigned {task.display_id} '{task.title}' in '{task.project.name}'.{due}",
           _task_url(task))


@login_required
def task_create(request, project_pk, parent_pk=None):
    project = _get_project(request, project_pk, manage=True)
    parent = None
    if parent_pk:
        parent = get_object_or_404(Task, pk=parent_pk, project=project, parent__isnull=True)
    form = TaskForm(request.POST or None, project=project, parent=parent)
    if request.method == "POST" and form.is_valid():
        task = form.save(commit=False)
        task.project = project
        task.parent = parent
        task.save()
        form.save_m2m()
        _notify_new_assignees(task, set())
        messages.success(request, f"{task.display_id} created.")
        return redirect(_task_url(parent, "subtasks") if parent else _project_url(project, "tasks"))
    return render(request, "projects/task_form.html",
                  {"form": form, "project": project, "parent": parent, "editing": False})


@login_required
def task_edit(request, pk):
    task = get_object_or_404(Task, pk=pk)
    project = _get_project(request, task.project_id, manage=True)
    previous = set(task.assigned_to.values_list("id", flat=True))
    form = TaskForm(request.POST or None, instance=task, project=project, parent=task.parent)
    if request.method == "POST" and form.is_valid():
        task = form.save()
        _notify_new_assignees(task, previous)
        messages.success(request, f"{task.display_id} updated.")
        return redirect(_task_url(task))
    return render(request, "projects/task_form.html",
                  {"form": form, "project": project, "parent": task.parent, "task": task, "editing": True})


@login_required
@require_POST
def task_delete(request, pk):
    task = get_object_or_404(Task, pk=pk)
    project = _get_project(request, task.project_id, manage=True)
    parent = task.parent
    task.delete()
    messages.success(request, "Task deleted.")
    return redirect(_task_url(parent, "subtasks") if parent else _project_url(project, "tasks"))


@login_required
def task_detail(request, pk):
    task = get_object_or_404(Task.objects.select_related("project", "parent"), pk=pk)
    project = _get_project(request, task.project_id)
    tab = request.GET.get("tab", "details")
    if tab not in ("details", "subtasks", "comments"):
        tab = "details"
    ctx = {
        "task": task, "project": project, "tab": tab,
        "can_manage": perm.can_manage(request.user, project),
        "can_update": perm.can_update_task(request.user, task),
        "can_contribute": perm.can_contribute(request.user, project),
        "lead_or_admin": perm.is_admin(request.user) or perm.is_lead(request.user, project),
        "unmet": task.unmet_dependencies(),
        "subtasks": task.subtasks.prefetch_related("assigned_to"),
        "comments": task.comments.select_related("author"),
        "comment_form": CommentForm(),
    }
    return render(request, "projects/task_detail.html", ctx)


@login_required
@require_POST
def task_status(request, pk):
    task = get_object_or_404(Task.objects.select_related("project"), pk=pk)
    project = _get_project(request, task.project_id)
    if not perm.can_update_task(request.user, task):
        raise PermissionDenied("Only assignees or the project lead can update this task's status.")
    new_status = request.POST.get("status")
    if new_status not in dict(Task.STATUS_CHOICES):
        messages.error(request, "Invalid status.")
    elif new_status == "completed" and task.unmet_dependencies().exists():
        ids = ", ".join(t.display_id for t in task.unmet_dependencies())
        messages.error(request, f"Complete the dependencies first: {ids}.")
    else:
        task.status = new_status
        task.save()
        if request.user.id != project.project_lead_id:
            notify([project.project_lead],
                   f"{request.user.display_name} marked {task.display_id} '{task.title}' as "
                   f"{task.get_status_display()}.", _task_url(task))
        messages.success(request, "Task status updated.")
    return redirect(_safe_next(request, _task_url(task)))


# ---------------------------------------------------------------- comments ----
@login_required
@require_POST
def comment_add(request, project_pk, task_pk=None):
    project = _get_project(request, project_pk, contribute=True)
    task = get_object_or_404(Task, pk=task_pk, project=project) if task_pk else None
    form = CommentForm(request.POST)
    if form.is_valid():
        c = form.save(commit=False)
        c.project, c.task, c.author = project, task, request.user
        c.save()
        where = f"{task.display_id}" if task else f"'{project.name}'"
        notify(project.member_users() - {request.user},
               f"{request.user.display_name} commented on {where}.",
               _task_url(task, "comments") if task else _project_url(project, "comments"))
        messages.success(request, "Comment added.")
    else:
        messages.error(request, "Comment can't be empty.")
    return redirect(_task_url(task, "comments") if task else _project_url(project, "comments"))


@login_required
@require_POST
def comment_delete(request, pk):
    c = get_object_or_404(Comment, pk=pk)
    project = _get_project(request, c.project_id)
    allowed = (perm.is_admin(request.user) or c.author_id == request.user.id
               or perm.is_lead(request.user, project))
    if not allowed or project.is_read_only:
        raise PermissionDenied
    task = c.task
    c.delete()
    messages.success(request, "Comment deleted.")
    return redirect(_task_url(task, "comments") if task else _project_url(project, "comments"))


# --------------------------------------------------------------- documents ----
@login_required
@require_POST
def document_upload(request, project_pk):
    project = _get_project(request, project_pk, contribute=True)
    form = DocumentForm(request.POST, request.FILES)
    if form.is_valid():
        f = form.cleaned_data["file"]
        Document.objects.create(
            project=project, uploaded_by=request.user, title=form.cleaned_data["title"],
            filename=os.path.basename(f.name)[:255],
            content_type=mimetypes.guess_type(f.name)[0] or "application/octet-stream",
            size=f.size, data=f.read(),
        )
        notify(project.member_users() - {request.user},
               f"{request.user.display_name} added a document to '{project.name}'.",
               _project_url(project, "documents"))
        messages.success(request, "Document uploaded.")
    else:
        for errs in form.errors.values():
            for e in errs:
                messages.error(request, e)
    return redirect(_project_url(project, "documents"))


@login_required
def document_download(request, pk):
    doc = get_object_or_404(Document, pk=pk)
    _get_project(request, doc.project_id)  # view permission check
    response = HttpResponse(bytes(doc.data), content_type=doc.content_type)
    response["Content-Disposition"] = content_disposition_header(True, doc.filename)
    response["X-Content-Type-Options"] = "nosniff"
    return response


@login_required
@require_POST
def document_delete(request, pk):
    doc = get_object_or_404(Document.objects.defer("data"), pk=pk)
    project = _get_project(request, doc.project_id)
    allowed = (perm.is_admin(request.user) or doc.uploaded_by_id == request.user.id
               or perm.is_lead(request.user, project))
    if not allowed or project.is_read_only:
        raise PermissionDenied
    doc.delete()
    messages.success(request, "Document deleted.")
    return redirect(_project_url(project, "documents"))


# ----------------------------------------------------------- notifications ----
@login_required
def notifications_list(request):
    items = request.user.notifications.all()[:100]
    return render(request, "projects/notifications.html", {"items": items})


@login_required
def notification_open(request, pk):
    n = get_object_or_404(Notification, pk=pk, user=request.user)
    n.is_read = True
    n.save(update_fields=["is_read"])
    return redirect(n.link or "notifications")


@login_required
@require_POST
def notifications_mark_all(request):
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return redirect(_safe_next(request, reverse("notifications")))
