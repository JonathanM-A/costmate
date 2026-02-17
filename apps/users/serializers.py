from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from dj_rest_auth.registration.serializers import RegisterSerializer
from allauth.account.adapter import get_adapter
from allauth.account.utils import setup_user_email
from allauth.account.models import EmailAddress
from .models import User, Business, UserPreferences, OnboardingMetrics
import logging

logger = logging.getLogger(__name__)


class UserSerializer(serializers.ModelSerializer):
    """Serializer for User model"""

    class Meta:
        model = User
        exclude = (
            "id",
            "groups",
            "user_permissions",
            "is_staff",
            "is_superuser",
            "last_login",
            "created_at",
            "updated_at",
            "is_active",
            "password",
            "stripe_customer_id",
            "staff_count",
        )


class CustomRegisterSerializer(RegisterSerializer):
    username = None  # Disable username field
    first_name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=True)
    personal_contact = serializers.CharField(required=True)

    def validate_email(self, email):
        """
        Checks if the email already exists in the EmailAddress model.
        This prevents creating a new user if an unverified email already exists,
        avoiding a database IntegrityError (500).
        """
        email = get_adapter().clean_email(email)

        # Check for existence of the email, regardless of verified status
        if EmailAddress.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError(
                ("A user is already registered with this e-mail address.")
            )
        return email

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


class BusinessSerializer(serializers.ModelSerializer):
    """Serializer for Business model"""

    class Meta:
        model = Business
        exclude = ("user", "created_at", "updated_at", "is_active")

    def validate_logo(self, value):
        """Validate that the uploaded logo has a valid content type."""
        if value:
            valid_content_types = ['image/jpeg', 'image/png']
            if value.content_type not in valid_content_types:
                raise ValidationError(
                    f"Unsupported file type. Allowed types: {', '.join(valid_content_types)}."
                )
        return value


class UserPreferencesSerializer(serializers.ModelSerializer):
    """Serializer for UserPreferences model"""

    class Meta:
        model = UserPreferences
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at")


class OnboardingMetricsSerializer(serializers.ModelSerializer):
    """Serializer for OnboardingMetrics model"""

    completion_percentage = serializers.ReadOnlyField()

    class Meta:
        model = OnboardingMetrics
        exclude = ["is_active", "created_at", "updated_at"]
        read_only_fields = ("user", "created_at", "updated_at")


FORMAT_MAPPING = {
    "DD": "%d",
    "MM": "%m",
    "YYYY": "%Y",
    "YY": "%y",
}


class UserFormattedDate(serializers.DateField):

    def _translate_format(self, user_format):
        """Custom DateField to format date according to user preferences"""
        python_format = user_format
        for key, value in FORMAT_MAPPING.items():
            python_format = python_format.replace(key, value)
        return python_format

    def to_representation(self, value):
        from .utils import get_user_preferrence_from_cache

        user = self.context["request"].user
        user_format = get_user_preferrence_from_cache(
            user.id, "date_format", "DD/MM/YYYY"
        )
        output_format = self._translate_format(user_format)

        if not value:
            return None
        try:
            return value.strftime(output_format)
        except Exception as e:
            logger.error(f"Error formatting date: {e}")
            return value.isoformat()
