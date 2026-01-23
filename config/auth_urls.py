from django.urls import path, include
from django.http import HttpResponseNotFound
from dj_rest_auth.views import (
    LoginView,
    PasswordChangeView,
    PasswordResetView,
    PasswordResetConfirmView,
    LogoutView,
)
from dj_rest_auth.registration.views import VerifyEmailView
from rest_framework_simplejwt.views import TokenRefreshView
from apps.users.views import CustomRegisterView, SessionView


# Dummy view for URL reversal (never actually called - users go to frontend)
def password_reset_confirm_redirect(_request, _uidb64, _token):
    return HttpResponseNotFound()


urlpatterns = [
    path("register/", CustomRegisterView.as_view(), name="register"),
    path(
        "password/reset/",
        PasswordResetView.as_view(),
        name="password_reset",
    ),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("session/", SessionView.as_view(), name="session"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("password/change/", PasswordChangeView.as_view(), name="password_change"),
    # Dummy URL for allauth's internal reverse() call - never visited
    path(
        "password/reset/confirm/<uidb64>/<token>/",
        password_reset_confirm_redirect,
        name="password_reset_confirm",
    ),
    # Actual API endpoint for password reset confirmation
    path(
        "password/reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="password_reset_confirm_api",
    ),
    path(
        "verify-email/",
        VerifyEmailView.as_view(),
        name="verify_email",
    ),
    path(
        "verify-email/<str:key>/",
        VerifyEmailView.as_view(),
        name="account_confirm_email",
    ),
]
