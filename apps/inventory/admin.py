from django.contrib import admin
from .models import InventoryItem, Supplier, Inventory, InventoryHistory


@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = ("name", "unit", "is_default", "created_by", "created_at")
    list_filter = ("is_default", "created_by")
    search_fields = ("name", "unit")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("Basic Information", {"fields": ("name", "unit", "is_default")}),
        (
            "System Information",
            {
                "fields": ("created_by", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "contact", "created_by", "created_at")
    search_fields = ("name", "contact")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("Basic Information", {"fields": ("name", "contact")}),
        (
            "System Information",
            {
                "fields": ("created_by", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "inventory_item",
        "quantity",
        "reorder_level",
        "is_below_reorder_level",
        "created_by",
    )
    list_filter = ("created_by", "inventory_item__is_default")
    search_fields = ("inventory_item__name",)
    readonly_fields = ("created_at", "updated_at", "is_below_reorder_level")
    fieldsets = (
        (
            "Stock Information",
            {"fields": ("inventory_item", "quantity", "reorder_level")},
        ),
        (
            "System Information",
            {
                "fields": ("created_by", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def is_below_reorder_level(self, obj):
        return obj.is_below_reorder_level

    is_below_reorder_level.boolean = True  # type: ignore
    is_below_reorder_level.short_description = "Below Reorder Level"  # type: ignore


@admin.register(InventoryHistory)
class InventoryHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "inventory_item",
        "quantity",
        "is_addition",
        "supplier",
        "cost_price",
        "cost_per_unit",
        "incident_date",
        "created_by",
    )
    list_filter = ("is_addition", "supplier", "incident_date", "created_by")
    search_fields = ("inventory_item__name", "supplier__name")
    readonly_fields = ("created_at", "updated_at", "cost_per_unit")
    date_hierarchy = "incident_date"
    fieldsets = (
        (
            "Transaction Information",
            {"fields": ("inventory_item", "quantity", "is_addition")},
        ),
        ("Purchase Details", {"fields": ("supplier", "cost_price", "cost_per_unit", "incident_date")}),
        (
            "System Information",
            {
                "fields": ("created_by", "created_at", "updated_at",),
                "classes": ("collapse",),
            },
        ),
    )
