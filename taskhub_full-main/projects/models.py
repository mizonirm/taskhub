from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL


class ProjectRequest(models.Model):
    STATUS_CHOICES = [("pending", "Pending"), ("approved", "Approved"), ("denied", "Denied")]

    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    due_date = models.DateField()
    project_lead = models.ForeignKey(User, on_delete=models.CASCADE, related_name="led_requests")
    faculty = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="requests_to_review",
        limit_choices_to={"role": "faculty"},
    )
    requested_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="submitted_requests")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"


class Project(models.Model):
    STATUS_CHOICES = [
        ("in_progress", "In Progress"),
        ("closure_requested", "Closure Requested"),
        ("closed", "Closed"),
    ]

    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    due_date = models.DateField()
    project_lead = models.ForeignKey(User, on_delete=models.CASCADE, related_name="led_projects")
    faculty = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="supervised_projects",
        limit_choices_to={"role": "faculty"},
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="in_progress")
    percent_complete = models.FloatField(default=0)
    source_request = models.OneToOneField(ProjectRequest, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_read_only(self):
        return self.status in ("closure_requested", "closed")

    def recalculate_completion(self):
        """Weighted % of top-level tasks completed (sub-tasks don't count toward the project)."""
        tasks = list(self.tasks.filter(parent__isnull=True))
        if not tasks:
            self.percent_complete = 0
        else:
            total = sum(t.percent_contribution for t in tasks)
            done = sum(t.percent_contribution for t in tasks if t.status == "completed")
            self.percent_complete = round(min(done / total, 1) * 100, 1) if total else 0
        self.save(update_fields=["percent_complete"])

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if kwargs.get("update_fields") is None:
            # The project lead must always be a member flagged as lead.
            self.members.exclude(user_id=self.project_lead_id).update(is_lead=False)
            ProjectMembership.objects.update_or_create(
                project=self, user_id=self.project_lead_id, defaults={"is_lead": True})

    def member_users(self):
        """Everyone who should hear about project-wide events: members + supervising faculty."""
        users = {m.user for m in self.members.select_related("user")}
        users.add(self.faculty)
        return users

    def __str__(self):
        return self.name


class ProjectMembership(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    is_lead = models.BooleanField(default=False)

    class Meta:
        unique_together = ("project", "user")

    def __str__(self):
        return f"{self.user} on {self.project}"


class Task(models.Model):
    STATUS_CHOICES = [("open", "Open"), ("in_progress", "In Progress"), ("completed", "Completed")]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="tasks")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE,
                               related_name="subtasks")
    title = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    depends_on = models.ManyToManyField("self", symmetrical=False, blank=True, related_name="blocks")
    percent_contribution = models.FloatField(
        default=10, help_text="Weight toward the project's overall % complete."
    )
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default="open")
    assigned_to = models.ManyToManyField(User, blank=True, related_name="tasks")
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def display_id(self):
        return f"TASK-{self.id}"

    @property
    def is_overdue(self):
        from django.utils import timezone
        return bool(self.due_date and self.status != "completed" and self.due_date < timezone.localdate())

    def unmet_dependencies(self):
        return self.depends_on.exclude(status="completed")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.project.recalculate_completion()

    def delete(self, *args, **kwargs):
        project = self.project
        super().delete(*args, **kwargs)
        project.recalculate_completion()

    def __str__(self):
        return f"{self.display_id}: {self.title}"


class Comment(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="comments")
    task = models.ForeignKey(Task, null=True, blank=True, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.author}: {self.body[:40]}"


class Document(models.Model):
    """Stored in the database so files survive on hosts with ephemeral disks."""
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="documents")
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=150)
    filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100, default="application/octet-stream")
    size = models.PositiveIntegerField(default=0)
    data = models.BinaryField()
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.title


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    message = models.CharField(max_length=300)
    link = models.CharField(max_length=200, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"To {self.user}: {self.message[:50]}"
