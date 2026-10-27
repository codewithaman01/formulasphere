import os
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_env_file(path):
    """Tiny .env reader (no extra package). Real environment variables always win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env_file(BASE_DIR / ".env")


def env(name, default=None):
    return os.environ.get(name, default)


def env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


DEBUG = env("DJANGO_DEBUG", "1") == "1"
TESTING = "test" in sys.argv

# On a real server (DJANGO_DEBUG=0) the secret key and the database connection string MUST come from .env.
SECRET_KEY = env("DJANGO_SECRET_KEY") or ("dev-only-secret-key-not-for-production-0123456789abcdef" if DEBUG else None)
if not SECRET_KEY or (not DEBUG and SECRET_KEY in ("change-me", "")):
    raise ImproperlyConfigured("Set DJANGO_SECRET_KEY in .env (see .env.example).")
ALLOWED_HOSTS = [h.strip() for h in env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [o.strip() for o in env("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]
SITE_URL = env("FS_SITE_URL", "http://localhost:8000").rstrip("/")     # used in emails and the sitemap

INSTALLED_APPS = [
    # Django's own apps need MongoDB-aware configs (ObjectId primary keys). See config/apps.py.
    "config.apps.MongoAdminConfig", "config.apps.MongoAuthConfig", "config.apps.MongoContentTypesConfig",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "django.contrib.sitemaps",
    "rest_framework", "rest_framework.authtoken",
    "taxonomy", "formulas", "accounts", "learning", "panel", "api", "web",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "panel.middleware.TwoFactorMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"], "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "panel.context.panel_menu",
        "web.context.site_context"]},
}]
# ---- Database: MongoDB Atlas. Put the connection string from Atlas (Connect -> Drivers) in .env as MONGODB_URI.
# >>> EDIT THIS ONE LINE: paste your Atlas connection string (Atlas -> Connect -> Drivers), with your password in it.
# If the password has special characters (@ : / ?) URL-encode them. No .env file is needed.
# (A MONGODB_URI environment variable, if you ever set one, takes priority over this line.)
MONGODB_URI = env(
    "MONGODB_URI",
    "mongodb+srv://aramanraj01_db_user:8amoG7hZujAXft75@cluster0.lgkxkcw.mongodb.net/?retryWrites=true&w=majority",
)
if "YOUR_PASSWORD" in MONGODB_URI or ".xxxxx." in MONGODB_URI:
    raise ImproperlyConfigured("Open config/settings.py and put your real Atlas connection string in MONGODB_URI "
                               "(replace YOUR_PASSWORD and cluster0.xxxxx.mongodb.net).")
DATABASES = {"default": {
    "ENGINE": "django_mongodb_backend",
    "HOST": MONGODB_URI,
    "NAME": env("MONGODB_NAME", "formulasphere"),
    "OPTIONS": {
        "retryWrites": True,
        "w": "majority",
        "serverSelectionTimeoutMS": env_int("MONGODB_TIMEOUT_MS", 10000),
        "socketTimeoutMS": 30000,
        "connectTimeoutMS": 10000,
    },
}}
# Django's own apps keep their migrations in a folder of this project, generated for MongoDB (ObjectId keys).
MIGRATION_MODULES = {
    "admin": "mongo_migrations.admin",
    "auth": "mongo_migrations.auth",
    "contenttypes": "mongo_migrations.contenttypes",
}
DEFAULT_AUTO_FIELD = "django_mongodb_backend.fields.ObjectIdAutoField"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "explore"
LOGOUT_REDIRECT_URL = "home"

# Business numbers
TRIAL_DAYS = env_int("FS_TRIAL_DAYS", 7)                      # free trial length for new sign-ups
PREMIUM_GRANT_DAYS = env_int("FS_PREMIUM_GRANT_DAYS", 30)             # days added by "Grant premium" in the panel
LOCKOUT_LIMIT = env_int("FS_LOCKOUT_LIMIT", 5)                   # wrong passwords / codes before a lock
LOCKOUT_IP_LIMIT = env_int("FS_LOCKOUT_IP_LIMIT", 30)               # wrong passwords from one address, any username
LOCKOUT_MINUTES = env_int("FS_LOCKOUT_MINUTES", 15)                # how long a lock lasts
EXPLORE_PAGE_SIZE = env_int("FS_EXPLORE_PAGE_SIZE", 12)              # formulas per page on the site and API
PANEL_PAGE_SIZE = env_int("FS_PANEL_PAGE_SIZE", 25)                # rows per page in the staff panel
LIVE_JOIN_EARLY_MINUTES = env_int("FS_LIVE_JOIN_EARLY_MINUTES", 15)        # meeting link appears this long before a live class
ENQUIRY_LIMIT = env_int("FS_ENQUIRY_LIMIT", 5)                   # tuition requests allowed per connection per hour
CURRENCY_SYMBOL = env("FS_CURRENCY_SYMBOL", "\u20b9")          # shown before every amount
PAYMENT_INSTRUCTIONS = env("FS_PAYMENT_INSTRUCTIONS", "Pay by UPI to your-id@bank and enter the payment reference below. Premium starts as soon as the payment is confirmed.")
PROTECT_CONTENT = env("FS_PROTECT_CONTENT", "1") == "1"              # blocks copy / select / print and adds a watermark on formula pages (deterrent only)
DEFAULT_ACCOUNT_TYPE = env("FS_DEFAULT_ACCOUNT_TYPE", "student")    # slug used when an old app sends no type

LANGUAGE_CODE = "en"
TIME_ZONE = "UTC"
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# Uploaded pictures now live in the database (web.StoredImage). MEDIA_ROOT is read ONLY once, by migration
# web.0005, to copy pictures uploaded before this update into the database. Nothing is served from it.
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")   # when behind nginx / a load balancer
X_FRAME_OPTIONS = "DENY"
if not DEBUG and not TESTING:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.TokenAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": EXPLORE_PAGE_SIZE,
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.AnonRateThrottle", "rest_framework.throttling.UserRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"anon": "30/min", "user": "120/min"},
}
# ---- Content protection and fair use
VIEW_LIMIT_PER_HOUR = env_int("FS_VIEW_LIMIT_PER_HOUR", 150)    # formula pages one non-staff account may open per hour
MAX_SESSIONS = env_int("FS_MAX_SESSIONS", 2)                    # devices signed in at once per non-staff account (0 = unlimited)
HEAVY_VIEWER_FLAG = env_int("FS_HEAVY_VIEWER_FLAG", 40)                # distinct formulas in 24 h that get an account flagged on the dashboard
SUBMISSIONS_PER_DAY = env_int("FS_SUBMISSIONS_PER_DAY", 5)      # formulas a student may submit per day

# ---- Email (console in development; set EMAIL_HOST etc. in .env on the server)
EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend" if DEBUG else "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", "localhost")
EMAIL_PORT = env_int("EMAIL_PORT", 587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env("EMAIL_USE_TLS", "1") == "1"
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "FormulaSphere <no-reply@formulasphere.local>")
REMINDER_TRIAL_DAYS = env_int("FS_REMINDER_TRIAL_DAYS", 2)       # email this many days before a trial ends
REMINDER_PREMIUM_DAYS = env_int("FS_REMINDER_PREMIUM_DAYS", 3)   # ... before Premium ends

# ---- Online payment (Razorpay). Leave the keys empty to keep the manual UPI flow only.
RAZORPAY_KEY_ID = env("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = env("RAZORPAY_KEY_SECRET", "")
RAZORPAY_WEBHOOK_SECRET = env("RAZORPAY_WEBHOOK_SECRET", "")
PAYMENT_CURRENCY = env("FS_PAYMENT_CURRENCY", "INR")

# ---- Backups (python manage.py backup_db). Atlas free clusters (M0) have no automatic backups, so run this nightly.
BACKUP_DIR = Path(env("FS_BACKUP_DIR", str(BASE_DIR / "backups")))
BACKUP_KEEP = env_int("FS_BACKUP_KEEP", 14)
