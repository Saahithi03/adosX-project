"""Django settings for the DealerOS reconciliation slice.

All secrets and connection strings come from the repo-root `.env`
(copied from `.env.example`). Nothing secret is hard-coded here.
"""
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
REPO_ROOT = BASE_DIR.parent

env = environ.Env()
# Real environment variables win over .env, so CI can override anything.
environ.Env.read_env(REPO_ROOT / ".env", overwrite=False)

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "rest_framework",
    "accounts",
    "tenancy",
    "recon",
    "ask",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Must follow AuthenticationMiddleware: it reads request.user.org_id.
    "tenancy.middleware.TenantMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": ["django.template.context_processors.request"]},
    },
]

# --- Database ---------------------------------------------------------------
# Two Postgres roles, one physical database (see docker/postgres/init/).
#   app   (default): the web server and the tests. RLS applies to it.
#   owner          : migrations, seed and ingest only. Selected explicitly with
#                    DEALEROS_DB_ROLE=owner, which the Makefile sets for those
#                    targets and nowhere else.
DB_ROLE = env("DEALEROS_DB_ROLE", default="app")
if DB_ROLE == "app":
    _db_url = env("DATABASE_URL_APP")
elif DB_ROLE == "owner":
    _db_url = env("DATABASE_URL_OWNER")
else:
    raise environ.ImproperlyConfigured(
        f"DEALEROS_DB_ROLE must be 'app' or 'owner', got {DB_ROLE!r}"
    )

DATABASES = {"default": env.db_url_config(_db_url)}
# Transactions are opened by TenantMiddleware (step 3), not per-request by
# Django, so that SET LOCAL and the view's queries share one transaction.
DATABASES["default"]["ATOMIC_REQUESTS"] = False
# No persistent connections for now; SET LOCAL keeps us safe either way.
DATABASES["default"]["CONN_MAX_AGE"] = 0

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Must be set before the first migration: swapping it later is painful.
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = []  # Seed users have demo passwords (alice123).

# --- DRF --------------------------------------------------------------------
REST_FRAMEWORK = {
    # Session auth runs in Django's middleware chain, so request.user is known
    # before TenantMiddleware sets the org. Token/JWT auth would run later,
    # inside the DRF view, and the middleware would see an anonymous user.
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    # JSON only: no browsable API, so no static files to serve.
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}

# --- LLM (/api/ask) -------------------------------------------------------------
# Empty or unset: /api/ask refuses with LLM_UNAVAILABLE; everything else works.
GEMINI_API_KEY = env("GEMINI_API_KEY", default="")
ASK_MODEL = env("ASK_MODEL", default="gemini-3.1-flash-lite")

# --- i18n / time ------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
# Timestamps (last_login, sessions) are aware; the business data uses plain
# DateFields, which are timezone-naive by nature.
USE_TZ = True
