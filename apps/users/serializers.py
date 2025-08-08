from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from dj_rest_auth.registration.serializers import RegisterSerializer
from allauth.account.adapter import get_adapter
from allauth.account.utils import setup_user_email
from .models import User, UserPreferences
import logging

logger = logging.getLogger(__name__)


class UserSerializer(serializers.ModelSerializer):
    """Serializer for User model"""

    class Meta:
        model = User
        exclude = ("groups", "user_permissions", "is_staff", "is_superuser")
        extra_kwargs = {
            "password": {"write_only": True},
        }
        read_only_fields = ("id", "is_active", "is_staff", "is_superuser")


class CustomRegisterSerializer(RegisterSerializer):
    username = None  # Disable username field
    first_name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=True)
    personal_contact = serializers.CharField(required=True)

    def get_cleaned_data(self):
        data = super().get_cleaned_data()
        data.update(
            {
                "first_name": self.validated_data.get("first_name", ""),  # type: ignore
                "last_name": self.validated_data.get("last_name", ""),  # type: ignore
                "personal_contact": self.validated_data.get("personal_constact"),  # type: ignore
            }
        )
        return data

    def save(self, request):
        adapter = get_adapter()
        user = adapter.new_user(request)
        self.cleaned_data = self.get_cleaned_data()

        # Save all fields to the user instance
        for key, value in self.cleaned_data.items():
            setattr(user, key, value)

        adapter.save_user(request, user, self, commit=False)

        # Perform password validation
        if "password1" in self.cleaned_data:
            try:
                adapter.clean_password(self.cleaned_data["password1"], user=user)
            except ValidationError as exc:
                raise serializers.ValidationError(
                    detail=serializers.as_serializer_error(exc)
                )

        user.save()
        self.custom_signup(request, user)
        setup_user_email(request, user, [])
        return user


class UserPreferencesSerializer(serializers.ModelSerializer):
    """Serializer for UserPreferences model"""

    class Meta:
        model = UserPreferences
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at")