from django.db import models
from django.contrib.auth.models import (
    AbstractBaseUser,
    PermissionsMixin,
    BaseUserManager,
)
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from ..common.models import BaseModel


class UserManager(BaseUserManager):
    def create_user(
        self,
        email: str,
        password: str,
        first_name: str,
        last_name: str,
        **extra_fields,
    ):
        if not all([email, password, first_name, last_name]):
            raise ValueError("All fields are required.")

        try:
            validate_password(password)
        except ValidationError as e:
            raise ValidationError(f"password: {e.messages}")

        user = self.model(
            email=self.normalize_email(email),
            first_name=first_name,
            last_name=last_name,
            **extra_fields,
        )
        user.set_password(password)
        user.full_clean()
        user.save()
        return user

    def create_superuser(
        self,
        email: str,
        password: str,
        first_name: str = "Admin",
        last_name: str = "User",
        **extra_fields,
    ):

        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_staff", True)

        # Create default business type if it doesn't exist
        default_business_type, _ = BusinessType.objects.get_or_create(
            code="admin", defaults={"name": "Admin Business", "is_default": True}
        )

        # Create default goal if it doesn't exist
        default_goal, _ = Goal.objects.get_or_create(
            code="admin", defaults={"name": "Admin Goal", "is_default": True}
        )

        # Set default values for required fields
        defaults = {
            "business_name": "Admin Business",
            "business_type": default_business_type,
            "primary_goal": default_goal,
            "location_country": "Administrative",
            "location_city": "Admin City",
            "opening_time": "09:00:00",
            "closing_time": "17:00:00",
            "preferred_currency": "USD",
            "staff_count": 1,
        }

        for key, value in defaults.items():
            extra_fields.setdefault(key, value)

        user = self.model(
            email=self.normalize_email(email),
            first_name=first_name,
            last_name=last_name,
            **extra_fields,
        )

        user.set_password(password)
        user.save()

        if not user.is_superuser:
            raise ValueError("Superuser must have is_superuser=True.")

        return user


class BusinessType(BaseModel):
    """Model to store business types with descriptions"""

    code = models.CharField(max_length=50, unique=True, blank=False)
    name = models.CharField(max_length=100, blank=False)
    description = models.TextField(blank=True, null=True)
    is_default = models.BooleanField(
        default=False,
        help_text="Indicates if this is a default business type that cannot be deleted.",
    )

    class Meta:  # type: ignore
        verbose_name = "Business Type"
        verbose_name_plural = "Business Types"

        ordering = ["name"]

    def __str__(self):
        return self.name


class Goal(BaseModel):
    """Model to store business goals"""

    code = models.CharField(max_length=50, unique=True, blank=False)
    name = models.CharField(max_length=100, unique=True, blank=False)
    description = models.TextField(blank=True, null=True)
    is_default = models.BooleanField(
        default=False,
        help_text="Indicates if this is a default goal that cannot be deleted.",
    )

    class Meta:  # type: ignore
        ordering = ["name"]

    def __str__(self):
        return self.name


class User(AbstractBaseUser, PermissionsMixin, BaseModel):
    first_name = models.CharField(max_length=50, blank=False)
    last_name = models.CharField(max_length=50, blank=False)
    email = models.EmailField(unique=True, blank=False)
    username = models.CharField(
        max_length=150,
        unique=True,
        blank=True,
        null=True
    )
    personal_contact = models.CharField(max_length=15, blank=True, null=True)
    business_contact = models.CharField(max_length=15, blank=True, null=True)
    business_name = models.CharField(max_length=100, blank=True, null=True)
    business_type = models.ForeignKey(
        BusinessType,
        on_delete=models.CASCADE,
        related_name="users",
        blank=True,
        null=True,
    )
    custom_business_type = models.CharField(
        max_length=100, blank=True, null=True
    )  # For custom business types not in the predefined list
    primary_goal = models.ForeignKey(
        Goal,
        on_delete=models.CASCADE,
        related_name="users",
        blank=True,
        null=True,
    )
    custom_primary_goal = models.CharField(max_length=100, blank=True, null=True)
    location_country = models.CharField(
        max_length=50, blank=True, null=True
    )  # Consider using a country choices field
    location_city = models.CharField(max_length=50, blank=True, null=True)
    opening_time = models.TimeField(blank=True, null=True)
    closing_time = models.TimeField(blank=True, null=True)
    social_media_links = models.JSONField(
        default=dict, blank=True, null=True
    )  # Store social media links as a JSON object
    preferred_currency = models.CharField(
        max_length=10, blank=True, null=True
    )  # Consider using a currency choices field
    staff_count = models.PositiveIntegerField(default=1, blank=True, null=True)
    biggest_challenge = models.TextField(blank=True, null=True, max_length=200)
    is_staff = models.BooleanField(
        default=False,
        help_text="Designates whether the user can log into this admin site.",
    )

    objects = UserManager()  # type: ignore

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    class Meta:  # type: ignore
        ordering = ["email"]

    @property
    def fullname(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def display_business_type(self):
        return (
            self.business_type.name if self.business_type else self.custom_business_type
        )

    @property
    def display_primary_goal(self):
        return self.primary_goal.name if self.primary_goal else self.custom_primary_goal

    def __str__(self):
        return f"{self.business_name} ({self.fullname})"
