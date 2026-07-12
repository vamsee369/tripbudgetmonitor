"""
Django settings for tripbudgetmonitor project.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
import dj_database_url

# ---------------------------
# Base directory & load .env FIRST
# ---------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")  # must run before any os.environ.get() calls

# ---------------------------
# Cloudinary (imported AFTER load_dotenv)
# ---------------------------
import cloudinary
import cloudinary.uploader
import cloudinary.api

cloudinary.config(
    cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
    api_key=os.environ.get("CLOUDINARY_API_KEY"),
    api_secret=os.environ.get("CLOUDINARY_API_SECRET"),
    secure=True,
)

# ---------------------------
# Security
# ---------------------------
SECRET_KEY = os.environ.get("SECRET_KEY")
DEBUG = False
ALLOWED_HOSTS = [
    'tripexpensetracker.onrender.com',
    "localhost",
    "127.0.0.1",
]

# ---------------------------
# Installed apps
# ---------------------------
INSTALLED_APPS = [
    "jazzmin",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "cloudinary_storage",            # must be before staticfiles
    "django.contrib.staticfiles",
    "cloudinary",
    "trip",
    "accounts",
]

# ---------------------------
# Middleware
# ---------------------------
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

ROOT_URLCONF = "tripbudgetmonitor.urls"

# ---------------------------
# Templates
# ---------------------------
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
            ],
        },
    }
]

WSGI_APPLICATION = "tripbudgetmonitor.wsgi.application"

# ---------------------------
# Database
# ---------------------------
DATABASES = {
    "default": dj_database_url.parse(
        os.getenv("DATABASE_URL")
    )
}

# ---------------------------
# Password validation
# ---------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------
# Internationalization
# ---------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

# ---------------------------
# Static & Media Storage
# ---------------------------
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"

# Django 4.2+ STORAGES dict (single source of truth — do NOT also set
# STATICFILES_STORAGE or DEFAULT_FILE_STORAGE, those are legacy aliases
# that conflict when STORAGES is present)
STORAGES = {
    "default": {
        # Media files → Cloudinary
        "BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage",
    },
    "staticfiles": {
        # CompressedStaticFilesStorage: gzip/br compress but NO manifest hashing.
        # Use this instead of CompressedManifestStaticFilesStorage to avoid the
        # FileNotFoundError during post_process on Render (manifest storage tries
        # to open files before they're fully written, and service-worker.js must
        # be served at a stable URL — hashing breaks SW registration).
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

# Legacy aliases required by django-cloudinary-storage 0.3.0 compatibility check.
# These MUST match what's in STORAGES above.
DEFAULT_FILE_STORAGE = "cloudinary_storage.storage.MediaCloudinaryStorage"
STATICFILES_STORAGE = "whitenoise.storage.CompressedStaticFilesStorage"

# Tell WhiteNoise not to crash if a file referenced in a manifest is missing.
# Safe to keep even with CompressedStaticFilesStorage (it's a no-op there).
WHITENOISE_MANIFEST_STRICT = False

# ---------------------------
# Default primary key
# ---------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------
# Login
# ---------------------------
LOGIN_URL = "/accounts/login/"

# ---------------------------
# HTTPS / Security Cookies
# ---------------------------
SECURE_SSL_REDIRECT = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# ---------------------------
# Jazzmin
# ---------------------------
JAZZMIN_SETTINGS = {
    "site_title": "Trip Budget Admin",
    "site_header": "Trip Budget Monitor",
    "site_brand": "TripBudget",
    "welcome_sign": "Welcome to Trip Budget Monitor Admin",
    "copyright": "Trip Budget Monitor",
    "topmenu_links": [
        {"name": "Home", "url": "admin:index"},
        {"name": "View Site", "url": "/", "new_window": True},
    ],
    "icons": {
        "auth": "fas fa-users-cog",
        "auth.user": "fas fa-user",
        "trip.trip": "fas fa-plane",
        "trip.expense": "fas fa-receipt",
        "trip.tripmember": "fas fa-users",
        "trip.splitbill": "fas fa-divide",
        "trip.settlementpayment": "fas fa-handshake",
    },
    "default_icon_parents": "fas fa-folder",
    "default_icon_children": "fas fa-circle",
    "show_sidebar": True,
    "navigation_expanded": True,
    "hide_apps": [],
    "hide_models": [],
    # Suppress the duplicate-file warnings for cancel.js / popup_response.js
    # (jazzmin and django.contrib.admin both ship these — jazzmin wins as it's
    # listed first in INSTALLED_APPS, which is intentional)
    "show_ui_builder": False,
}

JAZZMIN_UI_TWEAKS = {
    "theme": "flatly",
    "dark_mode_theme": "darkly",
    "navbar": "navbar-white navbar-light",
    "sidebar": "sidebar-light-primary",
    "brand_colour": "navbar-primary",
    "accent": "accent-primary",
    "button_classes": {
        "primary": "btn-primary",
        "secondary": "btn-secondary",
        "info": "btn-info",
        "warning": "btn-warning",
        "danger": "btn-danger",
        "success": "btn-success",
    },
}