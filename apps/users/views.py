from django.urls import reverse
from urllib.parse import urljoin
import requests
from rest_framework.response import Response
from rest_framework import status
from dj_rest_auth.registration.views import RegisterView
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from dj_rest_auth.registration.views import SocialLoginView
from .serializers import CustomRegisterSerializer, UserSerializer
from .models import User
import environ
import logging

env = environ.Env()
logger = logging.getLogger(__name__)


class CustomRegisterView(RegisterView):
    serializer_class = CustomRegisterSerializer


class UserRetrieveUpdateView(RetrieveUpdateAPIView):
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


class GoogleLoginView(SocialLoginView):
    """Google OAuth2 login view"""

    adapter_class = GoogleOAuth2Adapter
    client_class = CustomOAuth2Client
    callback_url = "http://localhost:8000/accounts/google/login/callback/"


class GoogleLoginCallback(APIView):
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):

        code = request.GET.get("code")
        logger.info("Google login callback received with code: %s", code)

        if code is None:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        # Remember to replace the localhost:8000 with the actual domain name before deployment
        token_endpoint_url = urljoin(
            "http://localhost:8000", reverse("auth:google_login")
        )
        response = requests.post(url=token_endpoint_url, data={"code": code})

        return Response(response, status=status.HTTP_200_OK)


# class GoogleLoginView(SocialLoginView):
#     """Google OAuth2 login view"""

#     adapter_class = GoogleOAuth2Adapter
#     client_class = CustomOAuth2Client
#     callback_url = "http://localhost:8000/accounts/google/login/callback/"

#     def post(self, request, *args, **kwargs):
#         serializer = self.get_serializer(data=request.data)
#         serializer.is_valid(raise_exception=True)

#         self.login(request)

#         from dj_rest_auth.utils import jwt_encode
#         from dj_rest_auth.app_settings import api_settings

#         if api_settings.USE_JWT:
#             access_token, refresh_token = jwt_encode(self.user)
#             return Response(
#                 {
#                     "access_token": str(access_token),
#                     "refresh_token": str(refresh_token),
#                     "user": {
#                         "id": self.user.id,
#                         "email": self.user.email,
#                         "username": self.user.username,
#                     },
#                 }
#             )


# class GoogleLoginCallback(APIView):
#     permission_classes = [AllowAny]

#     def get(self, request, *args, **kwargs):
#         logger.info("Google login callback received")

#         code = request.GET.get("code")

#         if code is None:
#             return Response(status=status.HTTP_400_BAD_REQUEST)

#         # Remember to replace the localhost:8000 with the actual domain name before deployment
#         token_endpoint_url = urljoin(
#             "http://localhost:8000", reverse("auth:google_login")
#         )
#         response = requests.post(url=token_endpoint_url, data={"code": code})

#         if response.status_code == 200:
#             return Response(response.json(), status=status.HTTP_200_OK)
#         else:
#             return Response(
#                 {"error": "Failed to retrieve access token"},
#                 status=response.status_code,
#             )
