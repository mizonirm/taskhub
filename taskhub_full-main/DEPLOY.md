# Deploying TaskHub

Recommended free-tier setup: **GitHub** (code) → **Render** (web app) → **Neon** (Postgres) → any **SMTP** account (OTP emails).
Check each provider's current free-plan terms before relying on them; they change.

## Things to know before you pick a host

- Render's free web service **sleeps after ~15 min idle** (first request then takes ~1 min) and has an **ephemeral disk** — that's why TaskHub stores documents in the database, not on disk.
- Render's own free Postgres **expires after 30 days**, so use an external Postgres such as Neon instead (this guide does).
- The app reads all settings from environment variables, so it also runs on Railway, Fly.io, PythonAnywhere, a VPS, etc.:
  build = `./build.sh`, start = `gunicorn taskhub_project.wsgi:application`.

## If someone will review it without you (e.g. your professor)

Nobody will be there to explain it or wake it up, so set it up to look after itself:

1. **Demo mode** — set `DEMO_MODE=True` (already preset in `render.yaml`). On every deploy this loads sample data
   (a faculty member, a project lead, two students, a half-finished project) and shows the demo logins plus a short
   "try this" guide on the login page. The reviewer can click straight in. New signups also work: with no email
   configured, the OTP is shown on the verification page, and the faculty approval gate is off so nobody gets stuck.
   **Demo mode publishes the demo password on the login page — only use it on a showcase site, never with real users.**
   Change the password with `DEMO_PASSWORD`.
2. **Keep it awake** — the free Render instance sleeps when idle, so a reviewer opening the link cold waits ~1 minute and may
   think it's broken. Fix: create a free account on an uptime monitor (UptimeRobot, cron-job.org, Better Stack…)
   and have it request `https://YOUR-APP.onrender.com/health/` every 5–10 minutes. (`/health/` needs no login and touches no data.)
   Alternative: Render's paid always-on plan — check the current price. Check the provider's current free-plan terms for both.
3. **Check it yourself the day before, and again right before you send the link** — open the URL on a phone (not your own
   laptop, so you see what a stranger sees), log in as `demo_prof` and `demo_alice`, mark a task completed, upload a file.
4. **Put the link and a 3-line note in your email/report**: "Log in as demo_prof / demo_lead / demo_alice / demo_bob,
   password …. Try: Campus Events App → Tasks → complete a task; as demo_lead request closure, as demo_prof approve it."
5. **Re-seeding** — the sample data is created once. If it gets messy after people play with it, delete the project in
   `/admin/` and redeploy (or run `python manage.py seed_demo` from a shell) to restore it.
6. **When the demo period is over**, set `DEMO_MODE=False` so the password disappears from the login page.

## 1. Put the code on GitHub

1. Create a GitHub account → **New repository** (private is fine).
2. Easiest: install **GitHub Desktop**, "Add local repository" → this folder → Publish.
   (`.gitignore` already excludes `venv`, `db.sqlite3`, `.env`.)

## 2. Create the Postgres database (Neon)

1. Sign up at neon.tech → create a project.
2. Copy the **connection string** (looks like `postgresql://user:pass@host/dbname?sslmode=require`). Keep it secret.

## 3. Create the web service (Render)

1. render.com → **New → Blueprint** → pick your repo (it reads `render.yaml`).
2. Fill in the environment variables it asks for (see `.env.example`):

| Variable | Value |
|---|---|
| `DATABASE_URL` | the Neon connection string |
| `ADMIN_USERNAME` / `ADMIN_EMAIL` / `ADMIN_PASSWORD` | your admin login (created automatically on each deploy) |
| `DEMO_MODE` | `True` for a showcase site (see above), `False` for real users |
| `ALLOWED_EMAIL_DOMAINS` | e.g. `youruniversity.edu` (comma-separate several; empty = any email) |
| `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` | your SMTP account (below) |

`SECRET_KEY` is generated for you; `DJANGO_DEBUG=False` is preset.

3. Deploy. The build installs packages, collects static files, migrates the database and creates the admin.
4. Open your `https://<name>.onrender.com/` URL and log in with the admin credentials.

## 4. Real OTP emails

OTP emails use Django's SMTP settings. Any SMTP provider works (Brevo, Mailgun, SendGrid, Gmail with an
*app password*, your college's SMTP). Set `EMAIL_HOST`, `EMAIL_PORT` (587), `EMAIL_HOST_USER`,
`EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`. Without `EMAIL_HOST`, codes only print in the server log.
**Test a real signup before announcing the site** — a sender address the provider hasn't verified is the usual failure.

## 5. Faculty approval (security)

Anyone can choose "Faculty" at signup, and Faculty can approve projects. In production TaskHub therefore holds
new faculty accounts until an admin approves them: **/admin/ → Users → tick the account → Action: "Approve selected faculty accounts"**.
You're notified in-app when someone is waiting. Set `FACULTY_REQUIRES_APPROVAL=False` to turn this off (not recommended for a public site).

## 6. After it's live

- Create a couple of test accounts end-to-end (student + faculty) on the live URL.
- Daily reminders for people who don't log in: add a scheduled job running `python manage.py send_due_reminders`
  (optional; reminders are created whenever someone opens their dashboard).
- Back up your database (Neon has its own tools) — documents and everything else live there.
- Updating the site: push to GitHub → Render redeploys → migrations run automatically.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Build fails: `SECRET_KEY environment variable is required` | `DJANGO_DEBUG=False` is set but `SECRET_KEY` is missing — add it. |
| "CSRF verification failed" on live site | Add `CSRF_TRUSTED_ORIGINS=https://your-domain` (not needed on `onrender.com`, it's automatic). |
| `DisallowedHost` | Add your domain to `ALLOWED_HOSTS` (comma-separated). |
| OTP email never arrives | Check SMTP credentials/sender verification; look at Render logs for the error. |
| Can't log in as new faculty | They're waiting for approval (section 5), unless `DEMO_MODE=True`. |
| Site slow on first visit | Free instance was asleep; it wakes in about a minute. |
