import os

from django import forms
from django.conf import settings

from accounts.models import User
from .models import Comment, Project, ProjectRequest, Task


class DateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, **kw):
        kw.setdefault("format", "%Y-%m-%d")
        super().__init__(**kw)


def _label_users(field):
    field.label_from_instance = lambda u: f"{u.display_name} ({u.email})"


class ProjectRequestForm(forms.ModelForm):
    class Meta:
        model = ProjectRequest
        fields = ["name", "description", "project_lead", "due_date", "faculty"]
        widgets = {"due_date": DateInput(), "description": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["project_lead"].queryset = User.objects.filter(role="member", is_active=True)
        self.fields["faculty"].queryset = User.objects.filter(role="faculty", is_active=True)
        _label_users(self.fields["project_lead"])
        _label_users(self.fields["faculty"])


class ProjectEditForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ["name", "description", "due_date"]
        widgets = {"due_date": DateInput(), "description": forms.Textarea(attrs={"rows": 4})}


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ["title", "description", "due_date", "depends_on",
                  "percent_contribution", "assigned_to", "status"]
        widgets = {"due_date": DateInput(), "description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, project, parent=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project
        self.parent = parent
        siblings = project.tasks.all()
        if self.instance.pk:
            siblings = siblings.exclude(pk=self.instance.pk)
        self.fields["depends_on"].queryset = siblings
        self.fields["assigned_to"].queryset = User.objects.filter(projectmembership__project=project)
        _label_users(self.fields["assigned_to"])
        if parent is not None or (self.instance.pk and self.instance.parent_id):
            # sub-tasks don't carry their own weight toward the project
            self.fields.pop("percent_contribution")

    def clean_percent_contribution(self):
        v = self.cleaned_data["percent_contribution"]
        if v < 0 or v > 100:
            raise forms.ValidationError("Enter a value between 0 and 100.")
        return v

    def clean_depends_on(self):
        deps = self.cleaned_data["depends_on"]
        if self.instance.pk:
            # reject cycles: A -> B -> ... -> A
            target = self.instance.pk
            for dep in deps:
                stack, seen = [dep], set()
                while stack:
                    cur = stack.pop()
                    if cur.pk == target:
                        raise forms.ValidationError(
                            f"{dep.display_id} already depends on this task (circular dependency).")
                    if cur.pk in seen:
                        continue
                    seen.add(cur.pk)
                    stack.extend(cur.depends_on.all())
        return deps

    def clean(self):
        data = super().clean()
        if data.get("status") == "completed" and data.get("depends_on") is not None:
            unmet = [d.display_id for d in data["depends_on"] if d.status != "completed"]
            if unmet:
                self.add_error("status", "Can't be completed until dependencies are done: "
                               + ", ".join(unmet))
        return data


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ["body"]
        widgets = {"body": forms.Textarea(attrs={"rows": 3, "placeholder": "Write a comment..."})}
        labels = {"body": ""}


class DocumentForm(forms.Form):
    title = forms.CharField(max_length=150)
    file = forms.FileField()

    def clean_file(self):
        f = self.cleaned_data["file"]
        ext = os.path.splitext(f.name)[1].lower()
        if ext not in settings.ALLOWED_DOCUMENT_EXTENSIONS:
            raise forms.ValidationError(
                "File type not allowed. Allowed: " + ", ".join(sorted(settings.ALLOWED_DOCUMENT_EXTENSIONS)))
        if f.size > settings.MAX_DOCUMENT_MB * 1024 * 1024:
            raise forms.ValidationError(f"File too large (max {settings.MAX_DOCUMENT_MB} MB).")
        return f


class AddMemberForm(forms.Form):
    user = forms.ModelChoiceField(queryset=User.objects.none(), label="Add team member")

    def __init__(self, *args, project, **kwargs):
        super().__init__(*args, **kwargs)
        existing = project.members.values_list("user_id", flat=True)
        self.fields["user"].queryset = User.objects.filter(role="member", is_active=True).exclude(id__in=existing)
        _label_users(self.fields["user"])
