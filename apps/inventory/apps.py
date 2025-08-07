from django.apps import AppConfig


class InventoryConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.inventory'

    def ready(self):
        import apps.inventory.signals  # Ensure signals are imported when the app is ready
