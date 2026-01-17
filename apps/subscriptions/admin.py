from django.contrib import admin
from .models import Subscription


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "tier",
        "current_sub_start",
        "current_sub_end",
        "is_active",
    )
    search_fields = (
        "user",
        "subscripition_code",
    )
    list_filter = ("current_sub_start", "current_sub_end", "is_active")
    ordering = ("current_sub_start",)
    readonly_fields = ("current_sub_start", "current_sub_end", "is_active")

    fieldsets = (
        (
            "Subscription Information",
            {
                "fields": (
                    "user",
                    "tier",
                    "current_sub_start",
                    "current_sub_end",
                    "is_active",
                    "is_cancelled",
                    "subscription_code"
                ),
            },
        ),
    )
