from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import InventoryHistory


@receiver(post_save, sender=InventoryHistory)
def update_inventory_values(sender, instance, **kwargs):
    """
    Update the total value and cost per unit of the inventory item after saving an InventoryHistory instance.
    """
    inventory_entry = instance.inventory_item.inventory.filter(
        created_by=instance.created_by
    ).first()
    print(instance.cost_per_unit)
    if not inventory_entry:
        return
    print("RUNNING:", inventory_entry.cost_per_unit)
    inventory_entry.calculate_cost()
