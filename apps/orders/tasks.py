from celery import shared_task
from django.db.models import F
from django.urls import reverse
from django.conf import settings
from ..notifications.models import Notification
from ..inventory.models import Inventory
from ..recipes.models import RecipeInventory
from ..users.utils import get_user_preferrence_from_cache
import logging
from datetime import timedelta
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def check_reorder_levels(self, order):
    """Check reorder levels after order completion"""

    retry_info = f" (Attempt {self.request.retries + 1} of {self.max_retries})"

    try:
        # Check user preferences for stock alerts
        notification_pref = get_user_preferrence_from_cache(
            order.created_by_id, "notification_preferences", default=dict()
        )
        if not notification_pref.get("stock_alerts", True):
            return

        # Get all InventoryItems used in the order (traverse: order -> products -> recipes -> ingredients)
        inventory_item_ids = (
            RecipeInventory.objects.filter(
                recipe__recipe_products__product__order_products__order=order
            )
            .values_list("inventory_item_id", flat=True)
            .distinct()
        )

        # Check which are below reorder level
        low_stock_count = Inventory.objects.filter(
            created_by=order.created_by,
            invetory_item_id__in=inventory_item_ids,
            quantity__lte=F("reorder_level"),
        ).count()

        if low_stock_count > 0:
            target_url = settings.BACKEND_DOMAIN_NAME + reverse("inventory-stock-list") + "?below_reorder=true"
            Notification.objects.create(
                user=order.created_by,
                notification_type="REORDER_CHECK",
                message=f"{low_stock_count} more items are below reorder level",
                content_object=order,
                target_url=target_url,
            )
    except Exception as e:
        logger.error(
            f"Error checking reorder levels for order {order.id}: {e}{retry_info}"
        )
        self.retry(exc=e)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def update_inventory_quantity(self, order, user):
    """Update inventory quantities based on the completed order"""

    retry_info = f" (Attempt {self.request.retries + 1} of {self.max_retries})"

    try:
        # Traverse: order -> products -> product_recipes -> recipe -> ingredients
        for order_product in order.order_products.all():
            order_qty = order_product.quantity
            for product_recipe in order_product.product.product_recipes.all():
                recipe_qty = product_recipe.quantity
                for ingredient in product_recipe.recipe.ingredients.all():
                    inventory = ingredient.inventory_item.inventory.get(created_by=user)
                    # Deduct: order_qty * product_recipe_qty * ingredient_qty
                    inventory.quantity -= ingredient.quantity * recipe_qty * order_qty
                    inventory.save()
    except Exception as e:
        logger.error(f"Error updating inventory for order {order.id}: {e}{retry_info}")
        self.retry(exc=e)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def estimate_stock_days_remaining(self, order):
    """Estimate days of stock remaining based on 90-day usage trends"""
    
    retry_info = f" (Attempt {self.request.retries + 1} of {self.max_retries})"
    
    try:
        from ..products.models import ProductRecipes

        ninety_days_ago = timezone.now() - timedelta(days=90)

        # Track processed inventory items to avoid duplicates
        processed_items = set()

        # Traverse: order -> products -> product_recipes -> recipe -> ingredients
        for order_product in order.order_products.all():
            for product_recipe in order_product.product.product_recipes.all():
                for ingredient in product_recipe.recipe.ingredients.all():
                    inventory_item = ingredient.inventory_item

                    # Skip if already processed
                    if inventory_item.id in processed_items:
                        continue
                    processed_items.add(inventory_item.id)

                    inventory = inventory_item.inventory.get(created_by=order.created_by)

                    # Calculate average daily usage over past 90 days
                    # Find all completed orders using this inventory item via products
                    total_used = 0
                    recipe_inventories = RecipeInventory.objects.filter(
                        inventory_item=inventory_item,
                        recipe__recipe_products__product__order_products__order__created_at__gte=ninety_days_ago,
                        recipe__recipe_products__product__order_products__order__status="completed",
                        recipe__recipe_products__product__order_products__order__created_by=order.created_by,
                    ).select_related("recipe")

                    for ri in recipe_inventories:
                        # Get all product_recipes and order_products for this recipe
                        for pr in ri.recipe.recipe_products.all():
                            for op in pr.product.order_products.filter(
                                order__created_at__gte=ninety_days_ago,
                                order__status="completed",
                            ):
                                total_used += ri.quantity * pr.quantity * op.quantity

                    avg_daily_usage = total_used / 90

                    if avg_daily_usage > 0:
                        days_remaining = inventory.quantity / avg_daily_usage

                        Notification.objects.create(
                            user=order.created_by,
                            notification_type="STOCK_ESTIMATE",
                            message=f"{inventory_item.name}: ~{int(days_remaining)} days of stock remaining",
                            target_url=settings.BACKEND_DOMAIN_NAME + reverse("inventory-stock-list"),
                        )
    except Exception as e:
        logger.error(
            f"Error estimating stock days for order {order.id}: {e}{retry_info}"
        )
        self.retry(exc=e)