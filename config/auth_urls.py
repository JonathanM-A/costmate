from django.urls import path, include
from dj_rest_auth.views import (
    LoginView,
    PasswordChangeView,
    PasswordResetView,
    PasswordResetConfirmView,
    LogoutView,
)
from dj_rest_auth.registration.views import VerifyEmailView
from rest_framework_simplejwt.views import TokenRefreshView
from apps.users.views import CustomRegisterView


urlpatterns = [
    path("register/", CustomRegisterView.as_view(), name="register"),
    path(
        "password/reset/",
        PasswordResetView.as_view(),
        name="password_reset",
    ),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("password/change/", PasswordChangeView.as_view(), name="password_change"),
    path(
        "password/reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
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
