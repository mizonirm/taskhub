"""All role rules in one place, so views stay readable and rules are easy to audit."""
from .models import ProjectMembership


def is_admin(user):
    return user.is_authenticated and user.is_admin_role


def is_member(user, project):
    return ProjectMembership.objects.filter(project=project, user=user).exists()


def is_lead(user, project):
    return ProjectMembership.objects.filter(project=project, user=user, is_lead=True).exists()


def is_project_faculty(user, project):
    return user.role == "faculty" and project.faculty_id == user.id


def can_view(user, project):
    return is_admin(user) or is_project_faculty(user, project) or is_member(user, project)


def can_manage(user, project):
    """Lead/admin may edit project, team, tasks — but not while the project is read-only."""
    return (is_admin(user) or is_lead(user, project)) and not project.is_read_only


def can_contribute(user, project):
    """Comment / upload documents: any participant, unless the project is read-only."""
    return can_view(user, project) and not project.is_read_only


def can_update_task(user, task):
    if task.project.is_read_only:
        return False
    return (is_admin(user) or is_lead(user, task.project)
            or task.assigned_to.filter(id=user.id).exists())


def visible_projects(user, queryset):
    if is_admin(user):
        return queryset
    if user.role == "faculty":
        return queryset.filter(faculty=user)
    return queryset.filter(members__user=user).distinct()
