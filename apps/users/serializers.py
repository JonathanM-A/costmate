from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from dj_rest_auth.registration.serializers import RegisterSerializer
from allauth.account.adapter import get_adapter
from allauth.account.utils import setup_user_email
from .models import User, BusinessType, Goal
import logging

logger = logging.getLogger(__name__)


class BusinessTypeSerializer(serializers.ModelSerializer):
    """Serializer for BusinessType model"""

    class Meta:
        model = BusinessType
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at")


class GoalSerializer(serializers.ModelSerializer):
    """Serializer for Goal model"""

    class Meta:
        model = Goal
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at")


class UserSerializer(serializers.ModelSerializer):
    """Serializer for User model"""

    business_type_detail = BusinessTypeSerializer(
        source="business_type", read_only=True
    )
    primary_goal_detail = GoalSerializer(source="primary_goal", read_only=True)

    class Meta:
        model = User
        exclude = ("groups", "user_permissions", "is_staff", "is_superuser")
        extra_kwargs = {
            "business_type": {"write_only": True, "required": False},
            "custom_business_type": {"write_only": True, "required": False},
            "primary_goal": {"write_only": True, "required": False},
            "custom_primary_goal": {"write_only": True, "required": False},
            "password": {"write_only": True},
        }
        read_only_fields = ("id", "is_active", "is_staff", "is_superuser")

    def validate(self, data):  # type: ignore

        # Validate business type and primary goal combinations
        logger.debug(f"Validating user data: {data}")

        business_type = data.get("business_type")
        custom_business_type = data.get("custom_business_type")
        primary_goal = data.get("primary_goal")
        custom_primary_goal = data.get("custom_primary_goal")

        try:
            # If custom type is provided, business_type should be "other"
            if custom_business_type:
                if not business_type or business_type != "other":
                    logger.warning(
                        f"Invalid business type combination: type={business_type}, custom={custom_business_type}"
                    )
                    raise serializers.ValidationError(
                        {
                            "error": "Must select 'Other' as business type when providing a custom type."
                        }
                    )

            # If business type is "other", custom type must be provided
            if business_type == "other" and not custom_business_type:
                logger.warning("Missing custom business type for 'other' selection")
                raise serializers.ValidationError(
                    {
                        "error": "Custom business type is required when 'Other' is selected."
                    }
                )

            # If custom primary goal is provided, primary_goal should be "other"
            if custom_primary_goal:
                if not primary_goal or primary_goal != "other":
                    logger.warning(
                        f"Invalid primary goal combination: goal={primary_goal}, custom={custom_primary_goal}"
                    )
                    raise serializers.ValidationError(
                        {
                            "error": "Must select 'Other' as primary goal when providing a custom goal."
                        }
                    )

            # If primary goal is "other", custom goal must be provided
            if primary_goal == "other" and not custom_primary_goal:
                logger.warning("Missing custom primary goal for 'other' selection")
                raise serializers.ValidationError(
                    {
                        "error": "Custom primary goal is required when 'Other' is selected."
                    }
                )

            logger.info("User data validation successful")
            return data

        except serializers.ValidationError as e:
            logger.error(f"Validation error: {str(e)}")
            raise

    def to_representation(self, instance):
        logger.debug(f"Converting user instance to representation: {instance.id}")
        try:
            representation = super().to_representation(instance)
            representation["business_type"] = instance.display_business_type
            representation["primary_goal"] = instance.display_primary_goal
            logger.debug(f"User representation created successfully: {representation}")
            return representation
        except Exception as e:
            logger.error(f"Error creating user representation: {str(e)}")
            raise


class CustomRegisterSerializer(RegisterSerializer):
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
