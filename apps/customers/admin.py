from django.contrib import admin
from django.contrib.auth import get_user_model
from .models import Customer

User = get_user_model()


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = (
        "first_name",
        "last_name",
        "contact",
        "email",
        "address",
    )

    search_fields = (
        "first_name",
        "last_name",
        "email",
        "contact",
        "address",
    )
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("Basic Information", {"fields": ("first_name", "last_name", "contact", "email"),}),
        (
            "Location Details",
            {"fields": ("address",)},
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

    def save_model(self, request, obj, form, change):
        if not change:  # If creating new object
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def formfield_for_choice_field(self, db_field, request, **kwargs):
        if db_field.name == "created_by":
            kwargs["choices"] = [
                (user.id)  # type: ignore
                for user in User.objects.filter(is_active=True)
            ]
        return super().formfield_for_choice_field(db_field, request, **kwargs)
