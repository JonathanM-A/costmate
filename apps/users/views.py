from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.conf import settings
from rest_framework.response import Response
from rest_framework import status
from rest_framework.generics import RetrieveUpdateAPIView, RetrieveAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from dj_rest_auth.registration.views import RegisterView
from dj_rest_auth.registration.views import SocialLoginView
import google.oauth2.credentials
import google.oauth2.id_token
import google.auth.transport.requests
from .serializers import (
    CustomRegisterSerializer,
    UserSerializer,
    User,
    UserPreferencesSerializer,
    UserPreferences,
)
from .utils import get_preferences_cache_key
import requests
import environ
import logging
import json

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


class CustomOAuth2Client(OAuth2Client):
    """Custom OAuth2Client that handles duplicate scope_delimiter parameter"""

    def __init__(self, *args, **kwargs):
        # Remove scope_delimiter from kwargs if it exists to avoid duplicate parameter
        kwargs.pop("scope_delimiter", None)
        super().__init__(*args, **kwargs)


class GoogleLogin(SocialLoginView):
    adapter_class = GoogleOAuth2Adapter
    callback_url = env.str(
        "GOOGLE_CALLBACK_URL",
        default="http://localhost:8000/accounts/google/login/callback/",  # type: ignore
    )
    client_class = CustomOAuth2Client


class GoogleCallbackView(APIView):
    permission_classes = [AllowAny]
    adapter_class = GoogleOAuth2Adapter

    def get(self, request, *args, **kwargs):
        try:
            code = request.query_params.get("code")
            if not code:
                return Response(
                    {"error": "Code parameter is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Get Google OAuth2 tokens
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
                return Response(
                    {"error": "Failed to get Google token"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Get user info from Google
            credentials = google.oauth2.credentials.Credentials(
                token_response.json()["access_token"]
            )
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

            # Generate JWT tokens
            refresh = RefreshToken.for_user(user)

            return Response(
                {
                    "refresh": str(refresh),
                    "access": str(refresh.access_token),
                    "user": {
                        "pk": user.id,  # type: ignore
                        "email": user.email,
                        "first_name": user.first_name,
                        "last_name": user.last_name,
                    },
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.error(f"Google callback error: {str(e)}")
            return Response(
                {"error": "Authentication failed"}, status=status.HTTP_400_BAD_REQUEST
            )


class UserPreferencesView(RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserPreferencesSerializer

    def get_object(self):  # type: ignore
        return self.request.user.preferences if hasattr(self.request.user, 'preferences') else None

    def get_queryset(self):
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
        cache_key = get_preferences_cache_key(request.user.id)
        cache.delete(cache_key)  # Invalidate cache on update

        response = super().update(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK:
            cache.set(cache_key, response.data, timeout=settings.CACHE_TIMEOUT)
        return response
