from datetime import timedelta

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from .models import Comment, Document, Notification, Project, ProjectMembership, ProjectRequest, Task

PW = "Str0ng-Pass!x"


def make_user(username, role="member", **kw):
    return User.objects.create_user(
        username=username, email=f"{username}@uni.edu", password=PW, role=role,
        is_active=True, is_email_verified=True, **kw)


class Base(TestCase):
    def setUp(self):
        self.faculty = make_user("prof", "faculty")
        self.lead = make_user("lead")
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        self.outsider = make_user("outsider")
        self.admin = User.objects.create_superuser("root", "root@uni.edu", PW)

    def login(self, user):
        self.client.logout()
        self.assertTrue(self.client.login(username=user.username, password=PW))

    def make_project(self):
        self.login(self.lead)
        self.client.post(reverse("request_project"), {
            "name": "Campus App", "description": "d", "project_lead": self.lead.id,
            "due_date": (timezone.localdate() + timedelta(days=5)).isoformat(), "faculty": self.faculty.id})
        req = ProjectRequest.objects.get()
        self.login(self.faculty)
        self.client.post(reverse("review_request", args=[req.id, "approve"]))
        self.project = Project.objects.get()
        self.login(self.lead)
        for u in (self.alice, self.bob):
            self.client.post(reverse("member_add", args=[self.project.id]), {"user": u.id})
        return self.project

    def make_task(self, title="T", weight=50, assignees=(), **extra):
        data = {"title": title, "description": "", "percent_contribution": weight,
                "status": "open", "assigned_to": [u.id for u in assignees], **extra}
        self.client.post(reverse("task_create", args=[self.project.id]), data)
        return Task.objects.filter(title=title).latest("id")


class SignupTests(TestCase):
    data = {"username": "newbie", "first_name": "N", "last_name": "B", "email": "newbie@uni.edu",
            "role": "member", "password1": PW, "password2": PW}

    def test_signup_otp_flow_sends_email_and_activates(self):
        r = self.client.post(reverse("signup"), self.data)
        self.assertRedirects(r, reverse("verify_otp"))
        user = User.objects.get(username="newbie")
        self.assertFalse(user.is_active)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(user.otp_code, mail.outbox[0].body)
        r = self.client.post(reverse("verify_otp"), {"code": user.otp_code})
        self.assertRedirects(r, reverse("dashboard"))
        user.refresh_from_db()
        self.assertTrue(user.is_active and user.is_email_verified)
        self.assertEqual(user.role, "member")

    def test_wrong_code_and_attempt_limit(self):
        self.client.post(reverse("signup"), self.data)
        user = User.objects.get(username="newbie")
        for _ in range(5):
            self.client.post(reverse("verify_otp"), {"code": "000000" if user.otp_code != "000000" else "111111"})
        r = self.client.post(reverse("verify_otp"), {"code": user.otp_code})
        self.assertContains(r, "Too many incorrect attempts")
        self.client.post(reverse("resend_otp"))
        user.refresh_from_db()
        r = self.client.post(reverse("verify_otp"), {"code": user.otp_code})
        self.assertRedirects(r, reverse("dashboard"))

    def test_expired_code(self):
        self.client.post(reverse("signup"), self.data)
        user = User.objects.get(username="newbie")
        user.otp_created_at = timezone.now() - timedelta(minutes=30)
        user.save()
        r = self.client.post(reverse("verify_otp"), {"code": user.otp_code})
        self.assertContains(r, "expired")

    @override_settings(ALLOWED_EMAIL_DOMAINS=["college.edu"])
    def test_domain_restriction(self):
        r = self.client.post(reverse("signup"), self.data)
        self.assertContains(r, "institutional email")
        self.assertFalse(User.objects.filter(username="newbie").exists())

    def test_unverified_signup_can_be_retried(self):
        self.client.post(reverse("signup"), self.data)
        self.client.logout()
        r = self.client.post(reverse("signup"), self.data)
        self.assertRedirects(r, reverse("verify_otp"))
        self.assertEqual(User.objects.filter(email="newbie@uni.edu").count(), 1)

    def test_superuser_gets_admin_role(self):
        u = User.objects.create_superuser("boss", "boss@uni.edu", PW)
        self.assertEqual(u.role, "admin")


class WorkflowTests(Base):
    def test_request_approval_creates_project_and_notifies(self):
        p = self.make_project()
        self.assertEqual(p.status, "in_progress")
        self.assertEqual(p.percent_complete, 0)
        self.assertTrue(ProjectMembership.objects.get(project=p, user=self.lead).is_lead)
        self.assertEqual(ProjectRequest.objects.get().status, "approved")
        self.assertTrue(Notification.objects.filter(user=self.faculty, message__contains="requested").exists())
        self.assertTrue(Notification.objects.filter(user=self.lead, message__contains="approved").exists())
        self.assertTrue(Notification.objects.filter(user=self.alice, message__contains="added").exists())

    def test_deny_and_no_double_review_and_post_only(self):
        self.login(self.lead)
        self.client.post(reverse("request_project"), {
            "name": "X", "description": "", "project_lead": self.lead.id,
            "due_date": "2030-01-01", "faculty": self.faculty.id})
        req = ProjectRequest.objects.get()
        self.login(self.faculty)
        self.assertEqual(self.client.get(reverse("review_request", args=[req.id, "deny"])).status_code, 405)
        self.client.post(reverse("review_request", args=[req.id, "deny"]))
        req.refresh_from_db()
        self.assertEqual(req.status, "denied")
        self.client.post(reverse("review_request", args=[req.id, "approve"]))
        self.assertEqual(Project.objects.count(), 0)
        self.assertTrue(Notification.objects.filter(user=self.lead, message__contains="denied").exists())

    def test_only_assigned_faculty_can_review(self):
        self.login(self.lead)
        self.client.post(reverse("request_project"), {
            "name": "X", "description": "", "project_lead": self.lead.id,
            "due_date": "2030-01-01", "faculty": self.faculty.id})
        req = ProjectRequest.objects.get()
        other = make_user("prof2", "faculty")
        self.login(other)
        self.assertEqual(self.client.post(reverse("review_request", args=[req.id, "approve"])).status_code, 403)
        self.login(self.alice)
        self.assertEqual(self.client.post(reverse("review_request", args=[req.id, "approve"])).status_code, 403)

    def test_faculty_cannot_request_projects(self):
        self.login(self.faculty)
        self.assertEqual(self.client.get(reverse("request_project")).status_code, 403)


class TaskTests(Base):
    def test_lead_creates_task_assignee_notified_with_due_date(self):
        p = self.make_project()
        t = self.make_task("Design", 50, [self.alice], due_date="2030-03-04")
        self.assertEqual(t.display_id, f"TASK-{t.id}")
        n = Notification.objects.get(user=self.alice, message__contains="assigned")
        self.assertIn("04 Mar 2030", n.message)

    def test_non_lead_cannot_create_or_edit(self):
        p = self.make_project()
        t = self.make_task("Design", 50, [self.alice])
        self.login(self.alice)
        self.assertEqual(self.client.get(reverse("task_create", args=[p.id])).status_code, 403)
        self.assertEqual(self.client.get(reverse("task_edit", args=[t.id])).status_code, 403)
        self.assertEqual(self.client.post(reverse("task_delete", args=[t.id])).status_code, 403)

    def test_status_update_rules_and_rollup(self):
        p = self.make_project()
        t1 = self.make_task("A", 30, [self.alice])
        t2 = self.make_task("B", 70, [self.bob])
        self.login(self.alice)
        self.client.post(reverse("task_status", args=[t1.id]), {"status": "completed"})
        p.refresh_from_db()
        self.assertEqual(p.percent_complete, 30.0)
        self.assertEqual(self.client.post(reverse("task_status", args=[t2.id]), {"status": "completed"}).status_code, 403)
        self.login(self.bob)
        self.client.post(reverse("task_status", args=[t2.id]), {"status": "completed"})
        p.refresh_from_db()
        self.assertEqual(p.percent_complete, 100.0)
        self.assertTrue(Notification.objects.filter(user=self.lead, message__contains="marked").exists())

    def test_dependency_blocks_completion_and_cycles_rejected(self):
        p = self.make_project()
        a = self.make_task("A", 50, [self.alice])
        b = self.make_task("B", 50, [self.alice], depends_on=[a.id])
        self.login(self.alice)
        self.client.post(reverse("task_status", args=[b.id]), {"status": "completed"})
        b.refresh_from_db()
        self.assertEqual(b.status, "open")
        self.client.post(reverse("task_status", args=[a.id]), {"status": "completed"})
        self.client.post(reverse("task_status", args=[b.id]), {"status": "completed"})
        b.refresh_from_db()
        self.assertEqual(b.status, "completed")
        self.login(self.lead)
        r = self.client.post(reverse("task_edit", args=[a.id]), {
            "title": "A", "description": "", "percent_contribution": 50, "status": "open",
            "depends_on": [b.id], "assigned_to": []})
        self.assertContains(r, "circular")

    def test_subtasks_dont_affect_project_percent(self):
        p = self.make_project()
        t = self.make_task("Parent", 100, [self.alice])
        self.client.post(reverse("subtask_create", args=[p.id, t.id]), {
            "title": "Sub", "description": "", "status": "completed", "assigned_to": [self.alice.id]})
        sub = Task.objects.get(title="Sub")
        self.assertEqual(sub.parent_id, t.id)
        p.refresh_from_db()
        self.assertEqual(p.percent_complete, 0)
        self.assertEqual(self.client.get(reverse("task_detail", args=[t.id]) + "?tab=subtasks").status_code, 200)

    def test_delete_task_recalculates(self):
        p = self.make_project()
        t1 = self.make_task("A", 50, [self.alice], status="completed")
        self.make_task("B", 50)
        p.refresh_from_db()
        self.assertEqual(p.percent_complete, 50.0)
        self.client.post(reverse("task_delete", args=[Task.objects.get(title="B").id]))
        p.refresh_from_db()
        self.assertEqual(p.percent_complete, 100.0)


class CommentDocumentTests(Base):
    def test_comments_by_roles_and_outsider_blocked(self):
        p = self.make_project()
        t = self.make_task("A", 100, [self.alice])
        for user in (self.faculty, self.alice, self.lead):
            self.login(user)
            self.client.post(reverse("comment_add", args=[p.id]), {"body": f"hi from {user.username}"})
            self.client.post(reverse("task_comment_add", args=[p.id, t.id]), {"body": f"task from {user.username}"})
        self.assertEqual(Comment.objects.filter(task__isnull=True).count(), 3)
        self.assertEqual(Comment.objects.filter(task=t).count(), 3)
        self.login(self.outsider)
        self.assertEqual(self.client.post(reverse("comment_add", args=[p.id]), {"body": "x"}).status_code, 403)
        self.assertEqual(self.client.get(reverse("project_detail", args=[p.id])).status_code, 403)

    def test_comment_delete_permissions(self):
        p = self.make_project()
        self.login(self.alice)
        self.client.post(reverse("comment_add", args=[p.id]), {"body": "mine"})
        c = Comment.objects.get()
        self.login(self.bob)
        self.assertEqual(self.client.post(reverse("comment_delete", args=[c.id])).status_code, 403)
        self.login(self.lead)
        self.client.post(reverse("comment_delete", args=[c.id]))
        self.assertEqual(Comment.objects.count(), 0)

    def test_document_upload_download_and_limits(self):
        p = self.make_project()
        self.login(self.alice)
        f = SimpleUploadedFile("plan.pdf", b"%PDF-1.4 hello", content_type="application/pdf")
        self.client.post(reverse("document_upload", args=[p.id]), {"title": "Plan", "file": f})
        d = Document.objects.get()
        self.login(self.faculty)
        r = self.client.get(reverse("document_download", args=[d.id]))
        self.assertEqual(r.content, b"%PDF-1.4 hello")
        self.assertIn("attachment", r["Content-Disposition"])
        self.login(self.outsider)
        self.assertEqual(self.client.get(reverse("document_download", args=[d.id])).status_code, 403)
        self.login(self.alice)
        bad = SimpleUploadedFile("evil.exe", b"MZ")
        self.client.post(reverse("document_upload", args=[p.id]), {"title": "bad", "file": bad})
        big = SimpleUploadedFile("big.pdf", b"x" * (5 * 1024 * 1024 + 1))
        self.client.post(reverse("document_upload", args=[p.id]), {"title": "big", "file": big})
        self.assertEqual(Document.objects.count(), 1)
        self.login(self.bob)
        self.assertEqual(self.client.post(reverse("document_delete", args=[d.id])).status_code, 403)
        self.login(self.lead)
        self.client.post(reverse("document_delete", args=[d.id]))
        self.assertEqual(Document.objects.count(), 0)


class ClosureTests(Base):
    def status(self, user, action, pid=None):
        self.login(user)
        return self.client.post(reverse("project_status", args=[pid or self.project.id]), {"action": action})

    def test_request_closure_flow_denied_then_approved(self):
        p = self.make_project()
        self.make_task("A", 100, [self.alice])
        self.assertEqual(self.status(self.alice, "request_closure").status_code, 403)
        self.status(self.lead, "close")
        p.refresh_from_db()
        self.assertEqual(p.status, "in_progress")  # <100% can't be closed directly
        self.status(self.lead, "request_closure")
        p.refresh_from_db()
        self.assertEqual(p.status, "closure_requested")
        self.assertTrue(Notification.objects.filter(user=self.faculty, message__contains="Closure requested").exists())
        # read-only enforcement
        self.login(self.lead)
        self.assertEqual(self.client.get(reverse("task_create", args=[p.id])).status_code, 403)
        self.assertEqual(self.client.post(reverse("comment_add", args=[p.id]), {"body": "x"}).status_code, 403)
        t = Task.objects.get()
        self.login(self.alice)
        self.assertEqual(self.client.post(reverse("task_status", args=[t.id]), {"status": "completed"}).status_code, 403)
        # faculty denies -> back to in progress, everyone notified
        self.assertEqual(self.status(self.alice, "deny_closure").status_code, 403)
        self.status(self.faculty, "deny_closure")
        p.refresh_from_db()
        self.assertEqual(p.status, "in_progress")
        for u in (self.alice, self.bob, self.lead):
            self.assertTrue(Notification.objects.filter(user=u, message__contains="not approved").exists())
        # request again, approve
        self.status(self.lead, "request_closure")
        self.status(self.faculty, "approve_closure")
        p.refresh_from_db()
        self.assertEqual(p.status, "closed")
        for u in (self.alice, self.bob):
            self.assertTrue(Notification.objects.filter(user=u, message__contains="approved").exists())
        self.assertEqual(self.client.get(reverse("project_list") + "?tab=closed").status_code, 200)
        # reopen
        self.status(self.alice, "reopen")
        p.refresh_from_db()
        self.assertEqual(p.status, "closed")
        self.status(self.lead, "reopen")
        p.refresh_from_db()
        self.assertEqual(p.status, "in_progress")

    def test_lead_closes_directly_at_100(self):
        p = self.make_project()
        t = self.make_task("A", 100, [self.alice], status="completed")
        self.status(self.lead, "request_closure")
        p.refresh_from_db()
        self.assertEqual(p.status, "in_progress")  # must use close at 100%
        self.status(self.lead, "close")
        p.refresh_from_db()
        self.assertEqual(p.status, "closed")


class VisibilityAndPagesTests(Base):
    def test_project_list_is_scoped_by_role(self):
        p = self.make_project()
        expectations = {self.lead: 1, self.alice: 1, self.faculty: 1, self.admin: 1, self.outsider: 0,
                        make_user("prof2", "faculty"): 0}
        for user, n in expectations.items():
            self.login(user)
            r = self.client.get(reverse("project_list"))
            self.assertEqual(len(r.context["projects"]), n, user.username)

    def test_upcoming_tab(self):
        p = self.make_project()  # due in 5 days
        self.login(self.lead)
        self.assertEqual(len(self.client.get(reverse("project_list") + "?tab=upcoming").context["projects"]), 1)
        p.due_date = timezone.localdate() + timedelta(days=60)
        p.save()
        self.assertEqual(len(self.client.get(reverse("project_list") + "?tab=upcoming").context["projects"]), 0)

    def test_every_page_renders_for_every_role(self):
        p = self.make_project()
        t = self.make_task("A", 100, [self.alice])
        self.client.post(reverse("comment_add", args=[p.id]), {"body": "c"})
        self.client.post(reverse("document_upload", args=[p.id]),
                         {"title": "d", "file": SimpleUploadedFile("a.txt", b"hi")})
        urls = [reverse("dashboard"), reverse("project_list"), reverse("notifications"),
                reverse("request_project")]
        urls += [reverse("project_detail", args=[p.id]) + f"?tab={x}" for x in ("details", "tasks", "comments", "documents")]
        urls += [reverse("task_detail", args=[t.id]) + f"?tab={x}" for x in ("details", "subtasks", "comments")]
        for user in (self.lead, self.alice, self.faculty, self.admin):
            self.login(user)
            for url in urls:
                if url == reverse("request_project") and user.role != "member":
                    continue
                self.assertEqual(self.client.get(url).status_code, 200, f"{user.username} {url}")

    def test_notifications_open_and_mark_read(self):
        self.make_project()
        self.login(self.alice)
        n = Notification.objects.filter(user=self.alice).first()
        r = self.client.get(reverse("notification_open", args=[n.id]))
        self.assertEqual(r.status_code, 302)
        n.refresh_from_db()
        self.assertTrue(n.is_read)
        self.login(self.bob)
        self.assertEqual(self.client.get(reverse("notification_open", args=[n.id])).status_code, 404)
        self.client.post(reverse("notifications_read_all"))
        self.assertFalse(Notification.objects.filter(user=self.bob, is_read=False).exists())

    def test_admin_can_manage_any_project(self):
        p = self.make_project()
        self.login(self.admin)
        self.client.post(reverse("project_edit", args=[p.id]), {"name": "Renamed", "description": "", "due_date": "2031-01-01"})
        p.refresh_from_db()
        self.assertEqual(p.name, "Renamed")
        self.client.post(reverse("project_delete", args=[p.id]))
        self.assertEqual(Project.objects.count(), 0)

    def test_root_redirects(self):
        self.assertRedirects(self.client.get("/"), reverse("login"), fetch_redirect_response=False)
        self.login(self.alice)
        self.assertRedirects(self.client.get("/"), reverse("dashboard"), fetch_redirect_response=False)


class InvariantAndReminderTests(Base):
    def test_lead_is_always_a_flagged_member(self):
        p = self.make_project()
        self.assertEqual(ProjectMembership.objects.filter(project=p, user=self.lead, is_lead=True).count(), 1)
        # projects created outside the request flow (e.g. Django admin) get it too
        p2 = Project.objects.create(name="Admin-made", due_date=timezone.localdate(),
                                    project_lead=self.alice, faculty=self.faculty)
        self.assertTrue(ProjectMembership.objects.get(project=p2, user=self.alice).is_lead)

    def test_requester_who_is_not_lead_becomes_member(self):
        self.login(self.alice)
        self.client.post(reverse("request_project"), {
            "name": "Alice's idea", "description": "", "project_lead": self.bob.id,
            "due_date": "2030-01-01", "faculty": self.faculty.id})
        req = ProjectRequest.objects.get()
        self.login(self.faculty)
        self.client.post(reverse("review_request", args=[req.id, "approve"]))
        p = Project.objects.get()
        self.assertTrue(ProjectMembership.objects.get(project=p, user=self.bob).is_lead)
        self.assertFalse(ProjectMembership.objects.get(project=p, user=self.alice).is_lead)

    def test_dashboard_creates_due_reminders_once(self):
        p = self.make_project()
        soon = (timezone.localdate() + timedelta(days=1)).isoformat()
        late = (timezone.localdate() - timedelta(days=2)).isoformat()
        self.make_task("Soon", 40, [self.alice], due_date=soon)
        self.make_task("Late", 60, [self.alice], due_date=late)
        self.login(self.alice)
        self.client.get(reverse("dashboard"))
        self.client.get(reverse("dashboard"))
        msgs = list(Notification.objects.filter(user=self.alice, message__regex=r"^(Reminder|Overdue)")
                    .values_list("message", flat=True))
        self.assertEqual(len([m for m in msgs if "'Soon'" in m]), 1)
        self.assertEqual(len([m for m in msgs if "'Late'" in m and m.startswith("Overdue")]), 1)
        # the scheduled-job command doesn't duplicate what the dashboard already created
        from django.core.management import call_command
        before = Notification.objects.filter(user=self.alice).count()
        call_command("send_due_reminders", verbosity=0)
        self.assertEqual(Notification.objects.filter(user=self.alice).count(), before)

    def test_no_reminders_for_completed_tasks_or_closed_projects(self):
        p = self.make_project()
        soon = (timezone.localdate() + timedelta(days=1)).isoformat()
        self.make_task("Done", 100, [self.alice], due_date=soon, status="completed")
        self.login(self.alice)
        self.client.get(reverse("dashboard"))
        self.assertFalse(Notification.objects.filter(user=self.alice, message__startswith="Reminder: TASK").exists())


class FacultyApprovalGateTests(TestCase):
    data = {"username": "profnew", "first_name": "P", "last_name": "N", "email": "profnew@uni.edu",
            "role": "faculty", "password1": PW, "password2": PW}

    def _signup_and_verify(self):
        self.client.post(reverse("signup"), self.data)
        user = User.objects.get(username="profnew")
        return user, self.client.post(reverse("verify_otp"), {"code": user.otp_code})

    @override_settings(FACULTY_REQUIRES_APPROVAL=False)
    def test_faculty_logs_straight_in_when_gate_is_off(self):
        user, r = self._signup_and_verify()
        self.assertRedirects(r, reverse("dashboard"))
        user.refresh_from_db()
        self.assertTrue(user.is_active)

    @override_settings(FACULTY_REQUIRES_APPROVAL=True)
    def test_faculty_waits_for_admin_when_gate_is_on(self):
        admin = User.objects.create_superuser("root", "root@uni.edu", PW)
        user, r = self._signup_and_verify()
        self.assertContains(r, "Waiting for admin approval")
        user.refresh_from_db()
        self.assertTrue(user.is_email_verified)
        self.assertFalse(user.is_active)
        self.assertTrue(Notification.objects.filter(user=admin, message__contains="awaiting approval").exists())
        # cannot log in yet, and the message says why
        r = self.client.post(reverse("login"), {"username": "profnew", "password": PW})
        self.assertContains(r, "waiting for admin approval")
        # admin approves via the admin action -> can log in
        self.client.login(username="root", password=PW)
        self.client.post("/admin/accounts/user/", {
            "action": "approve_faculty", "_selected_action": [user.pk]})
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.client.logout()
        self.assertTrue(self.client.login(username="profnew", password=PW))

    @override_settings(FACULTY_REQUIRES_APPROVAL=True)
    def test_students_are_never_gated(self):
        data = dict(self.data, username="stud", email="stud@uni.edu", role="member")
        self.client.post(reverse("signup"), data)
        user = User.objects.get(username="stud")
        r = self.client.post(reverse("verify_otp"), {"code": user.otp_code})
        self.assertRedirects(r, reverse("dashboard"))

    def test_unverified_login_gets_helpful_message(self):
        self.client.post(reverse("signup"), self.data)
        self.client.logout()
        r = self.client.post(reverse("login"), {"username": "profnew", "password": PW})
        self.assertContains(r, "verified yet")
        self.assertEqual(self.client.get(reverse("verify_otp")).status_code, 200)

    def test_wrong_password_reveals_nothing_about_account_state(self):
        self.client.post(reverse("signup"), self.data)
        self.client.logout()
        r = self.client.post(reverse("login"), {"username": "profnew", "password": "wrong-pass-123"})
        self.assertNotContains(r, "waiting for admin approval")
        self.assertNotContains(r, "verified yet")


class ErrorPageTests(Base):
    def test_custom_403_and_404_pages(self):
        p = self.make_project()
        self.login(self.outsider)
        self.assertContains(self.client.get(reverse("project_detail", args=[p.id])), "Access denied", status_code=403)
        self.assertContains(self.client.get("/projects/9999/"), "Page not found", status_code=404)


class DemoModeTests(TestCase):
    def test_health_endpoint_is_public(self):
        r = self.client.get("/health/")
        self.assertEqual((r.status_code, r.content), (200, b"ok"))

    @override_settings(DEMO_MODE=False)
    def test_seed_refuses_or_skips_when_demo_off(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            call_command("seed_demo", verbosity=0)
        call_command("seed_demo", "--if-demo", verbosity=0)  # silently skips
        self.assertEqual(Project.objects.count(), 0)

    @override_settings(DEMO_MODE=True, DEMO_PASSWORD="Pass-For-Demo-1")
    def test_demo_mode_seeds_shows_logins_and_ungates_faculty(self):
        from django.core.management import call_command
        call_command("seed_demo", "--if-demo", verbosity=0)
        call_command("seed_demo", "--if-demo", verbosity=0)  # idempotent
        self.assertEqual(Project.objects.count(), 1)
        self.assertTrue(self.client.login(username="demo_prof", password="Pass-For-Demo-1"))
        self.client.logout()
        page = self.client.get(reverse("login"))
        self.assertContains(page, "Demo site")
        self.assertContains(page, "demo_prof")
        self.assertContains(page, "Pass-For-Demo-1")

    @override_settings(DEMO_MODE=False)
    def test_login_page_has_no_demo_box_normally(self):
        self.assertNotContains(self.client.get(reverse("login")), "Demo site")


class DemoOtpOnScreenTests(TestCase):
    data = {"username": "newbie", "first_name": "N", "last_name": "B", "email": "newbie@uni.edu",
            "role": "member", "password1": PW, "password2": PW}

    def _code_shown(self):
        self.client.post(reverse("signup"), self.data)
        user = User.objects.get(username="newbie")
        page = self.client.get(reverse("verify_otp"))
        return user, (user.otp_code in page.content.decode())

    @override_settings(DEMO_MODE=True, EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend")
    def test_code_shown_in_demo_mode_without_email(self):
        user, shown = self._code_shown()
        self.assertTrue(shown)

    @override_settings(DEMO_MODE=False)
    def test_code_never_shown_outside_demo_mode(self):
        user, shown = self._code_shown()
        self.assertFalse(shown)

    @override_settings(DEMO_MODE=True, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_code_not_shown_when_real_email_is_configured(self):
        user, shown = self._code_shown()
        self.assertFalse(shown)
