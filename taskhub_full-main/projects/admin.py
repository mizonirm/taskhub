from django.contrib import admin

from .models import (Comment, Document, Notification, Project, ProjectMembership,
                     ProjectRequest, Task)


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "project", "uploaded_by", "size", "uploaded_at")
    exclude = ("data",)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "project_lead", "faculty", "status", "percent_complete", "due_date")
    list_filter = ("status",)


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("display_id", "title", "project", "parent", "status", "due_date")
    list_filter = ("status",)


admin.site.register(ProjectRequest)
admin.site.register(ProjectMembership)
admin.site.register(Comment)
admin.site.register(Notification)
