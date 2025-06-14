from .base import *  # noqa
import environ
import dj_database_url
from decouple import config

env = environ.Env()


DATABASES = {
    "default": dj_database_url.config(
        default=env("DATABSE_URL"),  # type: ignore
        conn_max_age=600,
        conn_health_checks=True,
    )
}


# SECURITY
# ------------------------------------------------------------------------------
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = config("DJANGO_SECURE_SSL_REDIRECT", default=True, cast=bool)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = config("DJANGO_CSRF_COOKIE_HTTPONLY", default=True, cast=bool)
CSRF_USE_SESSIONS = config("DJANGO_CSRF_USE_SESSION", default=True, cast=bool)
CSRF_COOKIE_SAMESITE = "Strict"
SESSION_COOKIE_HTTPONLY = config(
    "DJANGO_SESSION_COOKIE_HTTPONLY", default=True, cast=bool
)
SESSION_COOKIE_SAMESITE = "Strict"
X_FRAME_OPTIONS = "DENY"
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = config(
    "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", default=True, cast=bool
)
SECURE_HSTS_PRELOAD = config("DJANGO_SECURE_HSTS_PRELOAD", default=True, cast=bool)
SECURE_CONTENT_TYPE_NOSNIFF = config(
    "DJANGO_SECURE_CONTENT_TYPE_NOSNIFF", default=True, cast=bool
)
SECURE_BROWSER_XSS_FILTER = config(
    "DJANGO_SECURE_BROWSER_XSS_FILTER", default=True, cast=bool
)
SESSION_COOKIE_AGE = 25200  # 7 hours
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
CSP_INCLUDE_NONCE_IN = ("script-src", "style-src")
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CONTENT_TYPE_NOSNIFF = True

# FILE UPLOAD RESTRICTION---------------------SECURITY
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024  # 5.5 MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024  # 5.5 MB


# CORS
# ---------------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS", default=[], cast=lambda v: v.split(",")
)
CORS_ALLOW_CREDENTIALS = True
CORS_URLS_REGEX = r"^/api/.*$"
CORS_ALLOW_ALL_ORIGINS = config("CORS_ALLOW_ALL_ORIGINS", default=False, cast=bool)
CORS_ALLOWED_ORIGIN_REGEXES = [
    # r"^https://\w+\.example\.com$",
]
CORS_ALLOWED_METHODS = [
    "DELETE",
    "GET",
    "OPTIONS",
    "PATCH",
    "POST",
    "PUT",
]
CORS_ALLOWED_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
]
CORS_EXPOSE_HEADERS = [
    "Content-Range",
]
CORS_MAX_AGE = 86400  # 1 day
