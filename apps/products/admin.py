from django.contrib import admin
from .models import ProductCategory, Product, ProductRecipes


@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "created_by", "is_default", "created_at")
    list_filter = ("created_by", "is_default")
    search_fields = ("name",)
    fieldsets = (
        (None, {"fields": ("name", "is_default")}),
        ("Ownership", {"fields": ("created_by",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )
    readonly_fields = ("created_at", "updated_at")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category__name", "created_by", "total_cost", "recipes_count", "created_at")
    list_filter = ("created_by", "category__name")
    search_fields = ("name",)
    readonly_fields = ("recipes_cost", "labour_cost", "total_cost", "recipes_count", "created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("name", "category__name")}),
        ("Labour", {"fields": ("labour_time", "labour_rate", "labour_cost")}),
        ("Costs", {"fields": ("recipes_count", "recipes_cost", "total_cost")}),
        ("Ownership", {"fields": ("created_by",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )


@admin.register(ProductRecipes)
class ProductRecipesAdmin(admin.ModelAdmin):
    list_display = ("product", "recipe", "quantity", "cost", "created_by")
    list_filter = ("created_by",)
    search_fields = ("product__name", "recipe__name")
    readonly_fields = ("cost", "created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("product", "recipe", "quantity", "cost")}),
        ("Ownership", {"fields": ("created_by",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )
