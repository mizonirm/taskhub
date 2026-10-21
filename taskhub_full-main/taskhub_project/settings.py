"""
TaskHub settings.

Works locally with zero configuration (SQLite, console email, DEBUG on).
In production everything is controlled by environment variables — see DEPLOY.md.
"""
import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def env_list(name):
    return [x.strip() for x in os.environ.get(name, "").split(",") if x.strip()]


# "Production" = running on a host like Render (it sets RENDER=true) or DJANGO_ENV=production.
PRODUCTION = (
    os.environ.get("DJANGO_ENV", "").lower() == "production"
    or os.environ.get("RENDER", "").lower() == "true"
)
# Locally: DEBUG on. In production: DEBUG off unless you explicitly set DJANGO_DEBUG=true.
DEBUG = env_bool("DJANGO_DEBUG", not PRODUCTION)

SECRET_KEY = os.environ.get("SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "dev-only-insecure-key-change-me"
    else:
        raise RuntimeError("SECRET_KEY environment variable is required in production.")

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"] + env_list("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")
_render_host = os.environ.get("RENDER_EXTERNAL_HOSTNAME")  # set automatically on Render
if _render_host:
    ALLOWED_HOSTS.append(_render_host)
    CSRF_TRUSTED_ORIGINS.append(f"https://{_render_host}")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "projects",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "taskhub_project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "projects.context_processors.notifications",
            ],
        },
    },
]

WSGI_APPLICATION = "taskhub_project.wsgi.application"

# --- Database: SQLite locally, Postgres when DATABASE_URL is set -------------
DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
        conn_health_checks=True,
    )
}

AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.environ.get("TIME_ZONE", "Asia/Kolkata")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

from django.contrib.messages import constants as _msg  # noqa: E402
MESSAGE_TAGS = {_msg.ERROR: "danger"}

# --- TaskHub-specific ---------------------------------------------------------
# Comma-separated list, e.g. "youruni.edu,cs.youruni.edu". Empty = allow any email.
ALLOWED_EMAIL_DOMAINS = [d.lower().lstrip("@") for d in env_list("ALLOWED_EMAIL_DOMAINS")]
OTP_VALID_MINUTES = 10
OTP_MAX_ATTEMPTS = 5
MAX_DOCUMENT_MB = 5  # uploaded documents are stored in the database
ALLOWED_DOCUMENT_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".csv", ".txt",
    ".png", ".jpg", ".jpeg", ".zip",
}

# --- Email (OTP codes) ----------------------------------------------------------
# 1) BREVO_API_KEY set  -> real email over HTTPS (works on Render's free plan, which blocks SMTP)
# 2) EMAIL_HOST set     -> classic SMTP (works locally / on paid hosts)
# 3) neither            -> codes print in the server console/logs (fine for local demos)
if os.environ.get("BREVO_API_KEY"):
    EMAIL_BACKEND = "anymail.backends.brevo.EmailBackend"
    ANYMAIL = {"BREVO_API_KEY": os.environ["BREVO_API_KEY"]}
elif os.environ.get("EMAIL_HOST"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = os.environ["EMAIL_HOST"]
    EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
    EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "TaskHub <no-reply@taskhub.local>")

# Faculty can approve projects, so anyone choosing "Faculty" at signup is a privilege risk.
# When on, a new faculty account must be approved by an admin before it can log in.
# Default: OFF locally (smooth demos), ON in production. Override with FACULTY_REQUIRES_APPROVAL=True/False.
# DEMO_MODE: for a showcase deployment. Seeds sample data, shows demo logins on the login page,
# and disables the faculty gate so a reviewer can never get stuck. Never use it for real users.
DEMO_MODE = env_bool("DEMO_MODE", False)
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "Demo-Pass-123")
FACULTY_REQUIRES_APPROVAL = env_bool("FACULTY_REQUIRES_APPROVAL", not DEBUG and not DEMO_MODE)

# --- Production hardening (only when DEBUG is off) --------------------------------
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    SECURE_REDIRECT_EXEMPT = [r"^health/$"]  # uptime pingers / host health checks
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 3600

# Without this, a 500 error in production leaves no traceback in the host's log viewer.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {"django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False}},
}

# Tests create many users; the real password hasher is deliberately slow. Test runs only.
import sys  # noqa: E402
if "test" in sys.argv:
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
