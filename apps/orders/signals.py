from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Order
from .tasks import check_reorder_levels, update_inventory_quantity, estimate_stock_days_remaining


@receiver(post_save, sender=Order)
def post_order_completed(sender, instance, created, **kwargs):
    if instance.status == "completed" and not created:
        update_inventory_quantity.delay(instance, instance.created_by) #type: ignore
        check_reorder_levels.delay(instance.id)  # type: ignore
        estimate_stock_days_remaining.delay(instance)  # type: ignore

