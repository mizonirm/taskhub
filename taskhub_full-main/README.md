# TaskHub

Project management for student teams: request a project, get faculty approval, then manage
tasks, sub-tasks, comments and documents together. Django 5.2 · SQLite locally · PostgreSQL in production.

## Features (everything in the spec)

| Area | What it does |
|---|---|
| Sign up | Faculty / Team Member sign up with an institutional email + **6-digit OTP** (valid 10 min, 5 attempts, resend). Optional email-domain restriction. |
| Roles | **Admin** (everything, incl. Django admin panel) · **Faculty** (approve requests & closures, comment) · **Project Lead** (per project: team, tasks, edit/delete, close/reopen) · **Team Member** (request projects, update assigned tasks, comment, upload docs) |
| Project requests | Form → faculty is notified → approve/deny (POST, one-time) → requester notified → project created (status *In Progress*, 0%) |
| Projects | Tabs: **Project detail · Tasks · Comments · Documents**. Project list tabs: **All · Active · Upcoming · Closed** (each user sees only their own projects) |
| Tasks | Auto ID (`TASK-n`), description, due date, dependencies (no cycles; can't complete before dependencies), % weight, status, several assignees. **Sub-tasks** and task-level comments |
| Progress | Project % = weighted share of completed top-level tasks, updated automatically |
| Notifications | Request submitted/approved/denied, added to project, task assigned (with due date), status changes, comments, documents, closure events, due-soon/overdue reminders. Shown on the dashboard and a Notifications page |
| Documents | Upload (≤ 5 MB, allow-listed types); all project members can view/download. Stored in the database |
| Closure | Lead closes at 100%; below 100% the lead **requests closure** → project becomes **read-only** → faculty approves (Closed) or denies (back to In Progress) → all members notified. Lead can reopen a closed project |
| Dashboard | My Notifications · My Active Projects · My Tasks · My Project Requests (open only) · link to create a request · (faculty) approvals |

## Run it locally (Windows / VS Code)

If you already have the earlier MVP folder working, you only need steps 2–4 after replacing the files.

1. Open this folder in VS Code → terminal →
   `python -m venv venv` then `venv\Scripts\activate`
2. `pip install -r requirements.txt`
3. `python manage.py migrate`   (your existing data is kept; your admin account is upgraded to the Admin role automatically)
4. `python manage.py runserver` → open http://127.0.0.1:8000/

First time only: `python manage.py createsuperuser` (this account is the Admin).

**Demo data for your presentation:** `python manage.py seed_demo` (locally; on a deployed showcase site use `DEMO_MODE=True`, see DEPLOY.md) creates a faculty member, a project lead,
two students and a half-finished project. Log in as `demo_prof`, `demo_lead`, `demo_alice` or `demo_bob`
(password `Demo-Pass-123`). Outside local use it only runs when `DEMO_MODE=True`.

### Handy

- OTP codes print in the terminal running the server (until you configure real email — see DEPLOY.md).
- Admin panel: http://127.0.0.1:8000/admin/ — manage users, projects, tasks, comments, documents.
- Run the tests: `python manage.py test` (44 tests).
- Optional daily reminders for people who haven't logged in: `python manage.py send_due_reminders`
  (reminders are also created automatically when someone opens their dashboard).

## Walk-through for presenting (≈5 min)

1. Sign up as a Team Member and as Faculty (watch the OTP appear in the terminal).
2. Member → **New Project Request** → Faculty dashboard shows it (with a notification) → **Approve**.
3. Lead opens the project → **Tasks** → add tasks with weights, dependencies, assignees; add a sub-task.
4. Assignee marks tasks completed → project % moves. Try completing a task whose dependency is open.
5. Comments + a document upload. Show the Notifications page.
6. Lead → **Request closure** (project <100%) → project turns read-only → Faculty **Approves/Denies**.
7. Finish in `/admin/` to show the real database tables.

## Project layout

```
accounts/   users, roles, signup + OTP, login, dashboard
projects/   requests, projects, tasks, comments, documents, notifications
  permissions.py   every role rule in one file
  reminders.py     due-soon / overdue notifications
templates/  all pages (Bootstrap via CDN — restyle freely, logic is separate)
taskhub_project/settings.py   all configuration, driven by environment variables
```

## Known limits (be upfront about these if asked)

- Documents live in the database (simple and survives free-tier hosting), so keep files small. For heavy use, move to S3-style storage.
- "Upcoming" = active projects due within 14 days (the spec didn't define it; change `UPCOMING_DAYS` in `projects/views.py`).
- Replies/@-mentions on comments are the spec's "future enhancement" and are not built.
- Password reset by email isn't included; an admin can reset passwords in `/admin/`.
