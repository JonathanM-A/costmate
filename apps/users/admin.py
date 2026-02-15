from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Business, UserPreferences, OnboardingMetrics


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        "email",
        "first_name",
        "last_name",
    )
    search_fields = (
        "email",
        "first_name",
        "last_name",
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
                )
            },
        ),
        ("Permissions", {"fields": ("is_superuser",)}),
        ("Stripe", {"fields": ("stripe_customer_id", "has_used_free_trial")}),
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
                ),
            },
        ),
    )


@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ("user", "name", "country", "state", "email", "phone")
    search_fields = ("name", "user__email", "user__first_name", "user__last_name")
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (None, {"fields": ("user", "name")}),
        (
            "Location",
            {"fields": ("address", "country", "state")},
        ),
        (
            "Contact",
            {"fields": ("email", "phone")},
        ),
        (
            "Social Media",
            {"fields": ("facebook", "instagram", "x_twitter", "tiktok")},
        ),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )


@admin.register(UserPreferences)
class UserPreferencesAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "currency",
        "profit_margin",
        "labor_rate",
        "tax_enabled",
        "tax_rate",
    )
    list_filter = ("currency", "tax_enabled")
    search_fields = ("user__email", "user__first_name", "user__last_name")
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (None, {"fields": ("user",)}),
        (
            "Regional Settings",
            {"fields": ("currency", "date_format", "language", "time_zone")},
        ),
        (
            "Business Settings",
            {"fields": ("profit_margin", "labor_rate", "estimated_monthly_orders")},
        ),
        (
            "Tax Settings",
            {"fields": ("tax_enabled", "tax_rate")},
        ),
        (
            "Notifications",
            {"fields": ("notification_preferences",)},
        ),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )


@admin.register(OnboardingMetrics)
class OnboardingMetricsAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "has_entered_business_settings",
        "has_added_supplier",
        "has_added_inventory",
        "has_created_recipe",
        "has_calculated_overhead",
        "has_added_customer",
        "has_created_order",
        "completion_percentage",
    )
    list_filter = (
        "has_entered_business_settings",
        "has_added_supplier",
        "has_added_inventory",
        "has_created_recipe",
        "has_calculated_overhead",
        "has_added_customer",
        "has_created_order",
    )
    search_fields = ("user__email", "user__first_name", "user__last_name")
    readonly_fields = ("created_at", "updated_at", "completion_percentage")

    fieldsets = (
        (None, {"fields": ("user",)}),
        (
            "Setup Progress",
            {
                "fields": (
                    "has_entered_business_settings",
                    "has_added_supplier",
                    "has_added_inventory",
                    "has_created_recipe",
                    "has_calculated_overhead",
                    "has_added_customer",
                    "has_created_order",
                )
            },
        ),
        (
            "Completion",
            {"fields": ("completion_percentage",)},
        ),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def completion_percentage(self, obj):
        return f"{obj.completion_percentage}%"
    completion_percentage.short_description = "Completion"
