from django.contrib import admin
from .models import Recipe, RecipeInventory, RecipeCategory


class RecipeInventoryInline(admin.TabularInline):
    model = RecipeInventory
    extra = 1
    fields = ('inventory_item', 'quantity')


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'get_labour_time', 'total_cost', 'created_by', 'created_at')
    list_filter = ('created_by', 'category')
    search_fields = ('name',)
    readonly_fields = ('created_at', 'updated_at', 'inventory_items_cost', 'labour_cost', 'total_cost')
    inlines = [RecipeInventoryInline]
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'category', 'labour_time', 'labour_rate')
        }),
        ('Cost Information', {
            'fields': ('inventory_items_cost', 'labour_cost', 'total_cost'),
        }),
        ('Sharing', {
            'fields': ('is_public', 'share_enabled', 'share_token'),
        }),
        ('System Information', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_labour_time(self, obj):
        if not obj.labour_time:
            return "Not set"
        hours = obj.labour_time.seconds // 3600
        minutes = (obj.labour_time.seconds % 3600) // 60
        return f"{hours}h {minutes}m"
    get_labour_time.short_description = "Labour Time"  # type: ignore


@admin.register(RecipeInventory)
class RecipeInventoryAdmin(admin.ModelAdmin):
    list_display = ('recipe', 'inventory_item', 'quantity')
    list_filter = ('recipe', 'inventory_item')
    search_fields = ('recipe__name', 'inventory_item__name')
    raw_id_fields = ('recipe', 'inventory_item')


@admin.register(RecipeCategory)
class RecipeCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'created_by', 'created_at', 'is_default')
    search_fields = ('name',)
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Category Information', {
            'fields': ('name', 'description')
        }),
        ('System Information', {
            'fields': ('is_default', 'created_by', 'created_at', 'updated_at'),
        }),
    )