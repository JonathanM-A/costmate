from django.contrib import admin
from .models import Recipe, RecipeInventory


class RecipeInventoryInline(admin.TabularInline):
    model = RecipeInventory
    extra = 1
    fields = ('inventory_item', 'quantity')


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = ('name', 'get_labour_time', 'created_by', 'created_at')
    list_filter = ('created_by',)
    search_fields = ('name',)
    readonly_fields = ('created_at', 'updated_at')
    inlines = [RecipeInventoryInline]
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'labour_time')
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
