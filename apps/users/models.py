from django.db import models
from django.contrib.auth.models import (
    AbstractBaseUser,
    PermissionsMixin,
    BaseUserManager,
)
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from decimal import Decimal
from django.core.cache import cache
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

        UserPreferences.objects.create(user=user)

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

        user = self.model(
            email=self.normalize_email(email),
            first_name=first_name,
            last_name=last_name,
            **extra_fields,
        )

        user.set_password(password)
        user.save()

        UserPreferences.objects.create(id=user)

        if not user.is_superuser:
            raise ValueError("Superuser must have is_superuser=True.")

        return user


class User(AbstractBaseUser, PermissionsMixin, BaseModel):
    first_name = models.CharField(max_length=50, blank=False)
    last_name = models.CharField(max_length=50, blank=False)
    email = models.EmailField(unique=True, blank=False)
    personal_contact = models.CharField(max_length=15, blank=True, null=True)
    staff_count = models.PositiveIntegerField(default=1, blank=True, null=True)
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


ALLOWED_NOTIFICATION_KEYS = {"stock_alerts", "order_updates", "system_updates", "weekly_reports"}

class UserPreferences(BaseModel):
    id = None
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="preferences",
        primary_key=True,
    )
    currency = models.CharField(
        max_length=10,
        blank=True,
        null=True,
        default="GBP" # default to GBP, can be changed later
    )
    date_format = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        default="DD/MM/YYYY"  # default to UK date format, can be changed later
    )
    language = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        default="en"  # default to English, can be changed later
    )
    time_zone = models.CharField(
        max_length=10,
        blank=True,
        null=True,
        default="UTC"  # default to UTC, can be changed later
    )
    profit_margin = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=Decimal("30.00"), # default profit margin of 30%, can be changed later
        help_text="Default profit margin as a percentage (e.g., 30.00 for 30%)"
    )
    labor_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("15.00")  # default labor rate of £15.00, can be changed later
    )
    notification_preferences = models.JSONField(
        default=dict, blank=True, null=True
    )  # Store notification preferences as a JSON object

    def clean(self):
        super().clean()
        if self.notification_preferences:
            invalid_keys = set(self.notification_preferences.keys()) - ALLOWED_NOTIFICATION_KEYS
            if invalid_keys:
                raise ValidationError(
                    f"Invalid notification keys: {', '.join(invalid_keys)}. "
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

