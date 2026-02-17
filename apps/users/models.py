import os
import uuid
from django.db import models
from django.contrib.auth.models import (
    AbstractBaseUser,
    PermissionsMixin,
    BaseUserManager,
)
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from decimal import Decimal
from ..common.models import BaseModel
from .validators import (
    validate_logo_file_size,
    validate_logo_file_extension,
    validate_logo_dimensions,
)


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
    stripe_customer_id = models.CharField(max_length=100, blank=True, null=True)
    has_used_free_trial = models.BooleanField(default=False)

    objects = UserManager()  # type: ignore

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    class Meta:  # type: ignore
        ordering = ["email"]

    @property
    def fullname(self):
        return f"{self.first_name} {self.last_name}"


def logo_upload_path(instance, filename):
    """Generate upload path for logo files: logos/{user_pk}_{uuid}.{ext}"""
    ext = os.path.splitext(filename)[1]
    unique_filename = f"{instance.user.pk}_{uuid.uuid4()}{ext}"
    return os.path.join("logos", unique_filename)


class Business(BaseModel):
    id = None
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="business",
        primary_key=True,
    )
    name = models.CharField(max_length=100, blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    facebook = models.URLField(blank=True, null=True)
    instagram = models.URLField(blank=True, null=True)
    x_twitter = models.URLField(blank=True, null=True)
    tiktok = models.URLField(blank=True, null=True)
    logo = models.ImageField(
        upload_to=logo_upload_path,
        blank=True,
        null=True,
        validators=[
            validate_logo_file_size,
            validate_logo_file_extension,
            validate_logo_dimensions,
        ],
    )

    class Meta: # type: ignore
        verbose_name = "Business"
        verbose_name_plural = "Businesses"

    def __str__(self):
        return self.name or f"Business for {self.user.email}"

    def save(self, *args, **kwargs):
        """Override save to delete old logo file when a new one is uploaded."""
        if self.pk:
            try:
                old_instance = Business.objects.get(pk=self.pk)
                if old_instance.logo and old_instance.logo != self.logo:
                    # Delete the old logo file from storage
                    if old_instance.logo.storage.exists(old_instance.logo.name):
                        old_instance.logo.delete(save=False)
            except Business.DoesNotExist:
                pass
        super().save(*args, **kwargs)


ALLOWED_NOTIFICATION_KEYS = {"stock_alerts", "order_reminder", "system_updates", "weekly_reports"}

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
        max_digits=5,
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
        default=dict(stock_alerts=True, order_reminder=True, weekly_reports=True),
        blank=True,
        null=True,
    )  # Store notification preferences as a JSON object
    # {"stock_alerts": True, "order_reminder": False, "weekly_reports": True}
    tax_enabled = models.BooleanField(
        default=False,
        help_text="Indicates whether tax should be applied to orders.",
    )
    tax_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal(00.00),
        help_text="Tax rate as a percentage (e.g., 20.00 for 20%)"
    )
    estimated_monthly_orders = models.PositiveIntegerField(
        default=10,
        help_text="Estimated number of orders per month for subscription purposes.",
    )


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


class OnboardingMetrics(BaseModel):
    id = None
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="onboarding_metrics",
        primary_key=True,
    )
    # Step 1: Create your account - tracked by user creation itself
    # Step 2: Enter business (Settings)
    has_entered_business_settings = models.BooleanField(default=False)
    # Step 3: Add Supplier
    has_added_supplier = models.BooleanField(default=False)
    # Step 4: Add all inventory items from your recent purchase
    has_added_inventory = models.BooleanField(default=False)
    # Step 5: Create your first recipe
    has_created_recipe = models.BooleanField(default=False)
    # Step 6: Calculate overhead
    has_calculated_overhead = models.BooleanField(default=False)
    # Step 7: Create your first Product
    has_created_product = models.BooleanField(default=False)
    # Step 8: Add a customer
    has_added_customer = models.BooleanField(default=False)
    # Step 9: Create your first order
    has_created_order = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Onboarding Metrics"
        verbose_name_plural = "Onboarding Metrics"

    def __str__(self):
        return f"Onboarding metrics for {self.user.email}"

    @property
    def completion_percentage(self):
        """Calculate the percentage of onboarding steps completed."""
        steps = [
            True,  # Account created (always true if this record exists)
            self.has_entered_business_settings,
            self.has_added_supplier,
            self.has_added_inventory,
            self.has_created_recipe,
            self.has_calculated_overhead,
            self.has_added_customer,
            self.has_created_order,
        ]
        return str(int((sum(steps) / len(steps)) * 100)) + "%"



