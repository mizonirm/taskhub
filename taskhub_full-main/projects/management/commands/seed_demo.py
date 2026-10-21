"""
Fills the database with demo users, a project, tasks, comments — handy for presenting.
Local use only: refuses to run when DEBUG is off so demo passwords never reach production.
"""
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.models import User
from projects.models import Comment, Project, ProjectMembership, Task
from projects.notifications import notify



class Command(BaseCommand):
    help = "Create demo users/project/tasks (local use, or a deployment with DEMO_MODE=True)."

    def add_arguments(self, parser):
        parser.add_argument("--if-demo", action="store_true",
                            help="Do nothing (instead of failing) unless DEBUG or DEMO_MODE is on.")

    def handle(self, *args, **opts):
        if not (settings.DEBUG or settings.DEMO_MODE):
            if opts["if_demo"]:
                self.stdout.write("Demo mode is off; skipping demo data.")
                return
            raise CommandError("seed_demo only runs locally or when DEMO_MODE=True.")
        PASSWORD = settings.DEMO_PASSWORD
        if Project.objects.filter(name="Campus Events App").exists():
            self.stdout.write("Demo data already exists.")
            return

        def user(username, first, last, role):
            u, _ = User.objects.get_or_create(
                username=username,
                defaults=dict(email=f"{username}@demo.edu", first_name=first, last_name=last,
                              role=role, is_active=True, is_email_verified=True))
            u.set_password(PASSWORD)
            u.save()
            return u

        prof = user("demo_prof", "Priya", "Raman", "faculty")
        lead = user("demo_lead", "Arjun", "Kumar", "member")
        alice = user("demo_alice", "Alice", "Joseph", "member")
        bob = user("demo_bob", "Bala", "Singh", "member")

        today = timezone.localdate()
        project = Project.objects.create(
            name="Campus Events App", description="A mobile-friendly app to discover and RSVP to campus events.",
            due_date=today + timedelta(days=30), project_lead=lead, faculty=prof)
        # (the lead is added automatically when the project is saved)
        for u in (alice, bob):
            ProjectMembership.objects.get_or_create(project=project, user=u)

        def task(title, weight, status, who, days, deps=()):
            t = Task.objects.create(project=project, title=title, percent_contribution=weight,
                                    status=status, due_date=today + timedelta(days=days),
                                    description=f"{title} for the Campus Events App.")
            t.assigned_to.set(who)
            t.depends_on.set(deps)
            return t

        t1 = task("Gather requirements", 20, "completed", [lead], -3)
        t2 = task("Design wireframes", 25, "completed", [alice], 7, [t1])
        t3 = task("Build event listing page", 35, "in_progress", [bob, alice], 14, [t2])
        task("Write test plan", 20, "open", [bob], 21, [t3])
        Task.objects.create(project=project, parent=t3, title="Event card component", status="in_progress",
                            due_date=today + timedelta(days=10)).assigned_to.set([bob])
        Comment.objects.create(project=project, author=prof, body="Great start. Please share wireframes by Friday.")
        Comment.objects.create(project=project, task=t3, author=bob, body="Listing page layout is ready for review.")
        notify([alice, bob], f"You were added to the project '{project.name}'.", f"/projects/{project.pk}/")
        notify([bob], f"You were assigned {t3.display_id} '{t3.title}' in '{project.name}'.", f"/projects/tasks/{t3.pk}/")

        self.stdout.write(self.style.SUCCESS(
            f"Demo data created. Log in as demo_prof / demo_lead / demo_alice / demo_bob — password: {PASSWORD}"))
