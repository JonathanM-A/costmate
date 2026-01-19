from django.contrib import admin
from .models import Order, OrderRecipe


class RecipeInline(admin.TabularInline):
    model = OrderRecipe
    extra = 1
    readonly_fields = ("line_cost",)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_no",
        "customer",
        "final_price",
        "profit_margin",
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
        "subtotal",
        "total_cost",
        "order_price",
        "final_price",
        "vat_amount",
        "suggested_price",
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
            "Cost Breakdown",
            {
                "fields": ("subtotal", "overhead", "packaging", "total_cost"),
            },
        ),
        (
            "Pricing",
            {
                "fields": ("profit_margin", "order_price", "discount", "discount_is_percentage", "final_price"),
            },
        ),
        (
            "Tax & Final",
            {
                "fields": ("vat_rate", "vat_amount", "suggested_price", "preferred_final_price"),
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
    list_display = ("order__order_no", "recipe", "quantity", "line_cost")
    search_fields = ("order__order_no", "recipe__name")
    readonly_fields = ("line_cost",)

    fieldsets = (
        (
            "Order Recipe Information",
            {
                "fields": ("order", "recipe", "quantity", "line_cost"),
            },
        ),
    )
