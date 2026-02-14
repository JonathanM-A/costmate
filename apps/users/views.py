from urllib.parse import urlencode
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.conf import settings
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from django.shortcuts import redirect
from rest_framework.response import Response
from rest_framework import status
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from dj_rest_auth.registration.views import RegisterView
import google.oauth2.id_token
import google.auth.transport.requests
from .serializers import (
    CustomRegisterSerializer,
    UserSerializer,
    User,
    UserPreferencesSerializer,
    UserPreferences,
    OnboardingMetricsSerializer,
)
from .models import OnboardingMetrics
from .utils import get_preferences_cache_key
import requests
import environ
import logging

env = environ.Env()
logger = logging.getLogger(__name__)


class CustomRegisterView(RegisterView):
    serializer_class = CustomRegisterSerializer


class UserView(RetrieveUpdateAPIView):
    """ViewSet for User model"""

    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer
    queryset = User.objects.none()

    def get_object(self):  # type: ignore
        return self.request.user

    def get_queryset(self):  # type: ignore
        return User.objects.filter(id=self.request.user.id)  # type: ignore


class GoogleLoginRedirector(APIView):
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        client_id = env("GOOGLE_CLIENT_ID")
        redirect_uri = env(
            "GOOGLE_CALLBACK_URL",
            default="http://localhost:8000/accounts/google/login/callback/",  # type: ignore
        )

        signer = TimestampSigner()
        state = signer.sign("google-oauth")

        params = {
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "client_id": client_id,
            "scope": "openid email profile",
            "access_type": "online",
            "prompt": "select_account",
            "state": state,
        }

        google_auth_url = "https://accounts.google.com/o/oauth2/v2/auth"
        return redirect(f"{google_auth_url}?{urlencode(params)}")


class GoogleCallbackView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        try:
            # Verify state parameter to prevent CSRF
            state = request.query_params.get("state")
            if not state:
                return redirect(f"{settings.DOMAIN_NAME}/login?error=invalid_state")
            try:
                signer = TimestampSigner()
                signer.unsign(state, max_age=300)  # 5 minute expiry
            except (BadSignature, SignatureExpired):
                logger.warning("Google OAuth state invalid or expired")
                return redirect(f"{settings.DOMAIN_NAME}/login?error=invalid_state")

            code = request.query_params.get("code")
            if not code:
                return redirect(f"{settings.DOMAIN_NAME}/login?error=missing_code")

            # Exchange authorization code for tokens
            token_endpoint = "https://oauth2.googleapis.com/token"
            client_id = env("GOOGLE_CLIENT_ID")
            client_secret = env("GOOGLE_CLIENT_SECRET")
            redirect_uri = env(
                "GOOGLE_CALLBACK_URL",
                default="http://localhost:8000/accounts/google/login/callback/",  # type: ignore
            )

            token_response = requests.post(
                token_endpoint,
                data={
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )

            if token_response.status_code != 200:
                logger.error(f"Google token error: {token_response.text}")
                return redirect(f"{settings.DOMAIN_NAME}/login?error=token_exchange_failed")

            # Verify ID token with Google's public keys
            request_session = google.auth.transport.requests.Request()
            id_token = token_response.json()["id_token"]
            id_info = google.oauth2.id_token.verify_oauth2_token(
                id_token, request_session, client_id
            )

            # Get or create user
            User = get_user_model()
            try:
                user = User.objects.get(email=id_info["email"])
            except User.DoesNotExist:
                user = User.objects.create(
                    email=id_info["email"],
                    first_name=id_info.get("given_name", ""),
                    last_name=id_info.get("family_name", ""),
                )
                user.set_unusable_password()
                user.save(update_fields=["password"])

            # Generate JWT tokens and redirect to frontend
            refresh = RefreshToken.for_user(user)
            params = urlencode({
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            })
            return redirect(f"{settings.DOMAIN_NAME}/auth/callback?{params}")

        except Exception as e:
            logger.error(f"Google callback error: {str(e)}")
            return redirect(f"{settings.DOMAIN_NAME}/login?error=auth_failed")


class SessionView(APIView):
    """View to check authentication status and return user data"""
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        serializer = UserSerializer(request.user)
        return Response(
            {
                "status": "authenticated",
                "user": serializer.data
            },
            status=status.HTTP_200_OK
        )


class UserPreferencesView(RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserPreferencesSerializer

    def get_object(self):  # type: ignore
        return (
            self.request.user.preferences  # type:  ignore
            if hasattr(self.request.user, "preferences")
            else None
        )  

    def get_queryset(self): # type:  ignore
        user = self.request.user
        if not user.is_authenticated:
            return UserPreferences.objects.none()

        if hasattr(user, 'preferences'):
            return UserPreferences.objects.filter(user=user)

    def retrieve(self, request, *args, **kwargs):
        cache_key = get_preferences_cache_key(request.user.id)
        cached_data = cache.get(cache_key)

        if cached_data:
            return Response(cached_data, status=status.HTTP_200_OK)

        instance = self.get_object()
        serializer = self.get_serializer(instance)
        data = serializer.data

        cache.set(cache_key, data, timeout=settings.CACHE_TIMEOUT)
        return Response(data, status=status.HTTP_200_OK)

    def update(self, request, *args, **kwargs):
        cache_key = get_preferences_cache_key(request.user.id, settings.REST_FRAMEWORK["DEFAULT_VERSION"])
        cache.delete(cache_key)  # Invalidate cache on update

        response = super().update(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK:
            cache.set(cache_key, response.data, timeout=settings.CACHE_TIMEOUT)
            # Update onboarding metrics when business settings are updated
            if hasattr(request.user, "onboarding_metrics"):
                metrics = request.user.onboarding_metrics
                if not metrics.has_entered_business_settings:
                    metrics.has_entered_business_settings = True
                    metrics.save(update_fields=["has_entered_business_settings", "updated_at"])
        return response


class OnboardingMetricsView(RetrieveUpdateAPIView):
    """View for retrieving and updating onboarding metrics"""
    permission_classes = [IsAuthenticated]
    serializer_class = OnboardingMetricsSerializer

    def get_object(self):
        return (
            self.request.user.onboarding_metrics
            if hasattr(self.request.user, "onboarding_metrics")
            else None
        )

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return OnboardingMetrics.objects.none()

        if hasattr(user, "onboarding_metrics"):
            return OnboardingMetrics.objects.filter(user=user)
        return OnboardingMetrics.objects.none()
