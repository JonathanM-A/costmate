from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, BusinessType, Goal


@admin.register(BusinessType)
class BusinessTypeAdmin(admin.ModelAdmin):
    list_display = ("id","name", "code", "is_default")
    list_filter = ("is_default",)
    search_fields = ("name", "code", "description")
    ordering = ("name",)


@admin.register(Goal)
class GoalAdmin(admin.ModelAdmin):
    list_display = ("id","name", "code", "is_default")
    list_filter = ("is_default",)
    search_fields = ("name", "code", "description")
    ordering = ("name",)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        "email",
        "first_name",
        "last_name",
        "business_name",
        "business_type",
        "location_country",
    )
    list_filter = ("business_type", "location_country")
    search_fields = (
        "email",
        "first_name",
        "last_name",
        "business_name",
        "location_city",
    )
    ordering = ("email",)

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            "Personal Info",
            {
                "fields": (
                    "first_name",
                    "last_name",
                    "personal_contact",
                    "business_contact",
                )
            },
        ),
        (
            "Business Info",
            {
                "fields": (
                    "business_name",
                    "business_type",
                    "custom_business_type",
                    "primary_goal",
                    "custom_primary_goal",
                    "biggest_challenge"
                )
            },
        ),
        (
            "Location & Hours",
            {
                "fields": (
                    "location_country",
                    "location_city",
                    "opening_time",
                    "closing_time",
                )
            },
        ),
        ("Social Media", {"fields": ("social_media_links",)}),
        ("Permissions", {"fields": ("is_superuser",)}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "password1",
                    "password2",
                    "first_name",
                    "last_name",
                    "business_name",
                    "location_country",
                    "location_city",
                ),
            },
        ),
    )
