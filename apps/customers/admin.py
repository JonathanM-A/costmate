from django.contrib import admin
from django.contrib.auth import get_user_model
from .models import Customer, CustomerType

User = get_user_model()


@admin.register(CustomerType)
class CustomerTypeAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_default", "created_at", "updated_at")
    list_filter = ("is_default",)
    search_fields = ("code", "name", "description")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("Basic Information", {"fields": ("code", "name", "description")}),
        ("Settings", {"fields": ("is_default",)}),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "contact",
        "email",
        "customer_type",
        "location_city",
        "is_discount_eligible",
        "get_created_by_business",
    )
    list_filter = (
        "customer_type",
        "is_discount_eligible",
        "location_country",
        "created_by",
    )
    search_fields = (
        "name",
        "email",
        "contact",
        "location_city",
        "location_country",
        "created_by__business_name",
    )
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("Basic Information", {"fields": ("name", "contact", "email")}),
        (
            "Customer Classification",
            {
                "fields": (
                    "customer_type",
                    "custom_customer_type",
                    "is_discount_eligible",
                )
            },
        ),
        (
            "Location Details",
            {"fields": ("location_country", "location_city", "location_url")},
        ),
        (
            "System Information",
            {
                "fields": ("created_by", "created_at", "updated_at"),
            },
        ),
    )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "created_by":
            kwargs["queryset"] = User.objects.filter(is_active=True)
            kwargs["empty_label"] = None  # Makes the field required
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_created_by_business(self, obj):
        return obj.created_by.business_name if obj.created_by else ""

    get_created_by_business.short_description = "Created By"
    get_created_by_business.admin_order_field = "created_by__business_name"

    def save_model(self, request, obj, form, change):
        if not change:  # If creating new object
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def formfield_for_choice_field(self, db_field, request, **kwargs):
        if db_field.name == "created_by":
            kwargs["choices"] = [
                (user.id, user.business_name)
                for user in User.objects.filter(is_active=True)
            ]
        return super().formfield_for_choice_field(db_field, request, **kwargs)
