from django.db.models import F
from django.urls import reverse
from ..notifications.models import Notification
from ..inventory.models import Inventory
from ..recipes.models import RecipeInventory


class OrderNotificationService:
    @classmethod
    def check_reorder_levels(cls, order):
        """Check reorder levels after order completion"""
        # Get all InventoryItems used in the order
        inventory_item_ids = RecipeInventory.objects.filter(
            recipe__order_recipes__order=order
        ).values_list("inventory_item_id", flat=True).distinct()

        # Check which are below reorder level
        low_stock_count = Inventory.objects.filter(
            created_by=order.created_by,
            invetory_item_id__in=inventory_item_ids,
            quantity__lte=F("reorder_level")
        ).count()

        if low_stock_count > 0:
            target_url = reverse("inventory-stock-list") + "?below_reorder=true"
            Notification.objects.create(
                user=order.created_by,
                notification_type="REORDER_CHECK",
                message=f"{low_stock_count} more items are below reorder level",
                content_object=order,
                target_url=target_url
            )