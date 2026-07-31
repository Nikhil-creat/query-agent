"""
Django settings for the data-chat-agent backend.

Kept intentionally minimal (single app, SQLite, no auth) since the scope
of this project is the NL->SQL agent pipeline itself, not a production
Django deployment. See README.md "Taking this further" for what a
production hardening pass would add (auth, Postgres, per-user datasets).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-secret-do-not-use-in-production")
DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() == "true"

# Comma-separated in production, e.g. "data-chat-agent.onrender.com".
# Defaults to "*" for local development only.
ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")
    if h.strip()
] or ["*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "core",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
]

# The frontend runs on a different origin (localhost:5173 in dev, your
# Vercel domain in production), so CORS must be opened explicitly.
# Set CORS_ALLOWED_ORIGINS=https://your-app.vercel.app in production.
CORS_ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if o.strip()
]

ROOT_URLCONF = "dataagent.urls"
WSGI_APPLICATION = "dataagent.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "data" / "app.sqlite3",
    }
}
(BASE_DIR / "data").mkdir(exist_ok=True)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
        "rest_framework.parsers.FormParser",
    ],
}

# Kept mainly so DRF's browsable API renders with CSS in production too.
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
