from django.contrib import admin
from .models import Order, OrderRecipe


class RecipeInline(admin.TabularInline):
    model = OrderRecipe
    extra = 1
    readonly_fields = ("line_value",)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_no",
        "customer",
        "total_value",
        "tax_amount",
        "status",
        "delivery_date",
        "created_at",
    )
    search_fields = ("order_no", "customer__name")
    list_filter = ("status", "delivery_date", "created_at")
    inlines = [RecipeInline]
    ordering = ("-created_at",)
    readonly_fields = (
        "created_at",
        "updated_at",
        "total_value",
        "tax_amount",
        "profit",
        "profit_percentage",
        "order_no",
    )

    fieldsets = (
        (
            "Order Information",
            {
                "fields": ("customer", "delivery_date", "status"),
            },
        ),
        (
            "Financial Information",
            {
                "fields": ("total_value", "tax_amount", "profit", "profit_percentage"),
            },
        ),
        (
            "System Information",
            {
                "fields": ("order_no", "created_by", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(OrderRecipe)
class OrderRecipeAdmin(admin.ModelAdmin):
    list_display = ("order__order_no", "recipe", "quantity", "line_value")
    search_fields = ("order__order_no", "recipe__name")
    readonly_fields = ("line_value",)

    fieldsets = (
        (
            "Order Recipe Information",
            {
                "fields": ("order", "recipe", "quantity", "line_value"),
            },
        ),
    )
